#weekly_stats.py

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import asyncio
import time

class WeeklyStats(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    async def cog_load(self):
        self.weekly_recap_loop.start()

    def cog_unload(self):
        self.weekly_recap_loop.cancel()

    # --- COMMANDS ---

    @app_commands.command(name="weekly_leaderboard", description="🏆 Ringkasan keaktifan komunitas selama minggu ini.")
    async def weekly_lb(self, interaction: discord.Interaction):
        # 1. PRIORITAS UTAMA: Lapor ke Discord (ACK)
        # Harus paling atas. Jangan ada logika lain sebelumnya.
        try:
            await interaction.response.defer(thinking=True)
            # Log bahwa kita berhasil lapor
            self.bot.logger.info("INTERACTION", f"ACK Success: {interaction.user.id}")
        except discord.InteractionResponded:
            # Sudah di-ack duluan (jarang, tapi aman)
            pass
        except Exception as e:
            # Jika ACK gagal, bot tidak bisa lanjut. Log dan stop.
            self.bot.logger.error("INTERACTION_FAIL", "Defer Gagal", error_obj=e)
            return

        # 2. BARU JALANKAN LOGIKA & BENCHMARK
        start_time = time.time()
        
        guild = interaction.guild
        current_week = self.db.get_current_week_key()
        
        # --- 1. AMBIL SUMMARY SERVER (Total minggu ini) ---
        totals = await self.db.fetch_one("""
            SELECT 
                COALESCE(SUM(weekly_voice_mins),0) as total_voice,
                COALESCE(SUM(weekly_chat_xp),0) as total_chat_xp,
                COALESCE(SUM(weekly_xp),0) as total_xp
            FROM weekly_stats 
            WHERE guild_id = ? AND week_key = ?
        """, (guild.id, current_week))
        
        # --- 2. AMBIL TOP 10 USER ---
        # Sorting: Voice Mins -> Total XP -> User ID
        top_users = await self.db.fetch_all("""
            SELECT user_id, weekly_voice_mins, weekly_xp, weekly_chat_xp
            FROM weekly_stats 
            WHERE guild_id = ? AND week_key = ? 
            ORDER BY weekly_voice_mins DESC, weekly_xp DESC, user_id ASC
            LIMIT 10
        """, (guild.id, current_week))

        if not top_users:
            try:
                await interaction.followup.send("💤 Belum ada aktivitas minggu ini. Ayo ramaikan Voice & Chat!", ephemeral=True)
            except:
                pass
            return 
        
        # --- [BARU] 2.5 AMBIL RANKING GLOBAL ---
        global_rank, total_servers = await self.db.get_guild_weekly_rank(guild.id, current_week)

        # --- 3. RENDER EMBED ---
        # Header Summary
        t_voice = totals['total_voice']
        t_chat = totals['total_chat_xp']
        t_xp = totals['total_xp']
        
        desc = f"**Statistik Server Minggu Ini:**\n🎙️ `{t_voice:,}m`   💬 `{t_chat:,} XP`   ✨ `{t_xp:,} XP`\n\n"
        desc += "**🏆 Top 10 Contributors:**\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, row in enumerate(top_users):
            user_id = row['user_id']
            mins = row['weekly_voice_mins']
            chat_xp = row['weekly_chat_xp']
            total_xp = row['weekly_xp']
            
            # Fetch user (handle user left)
            member = guild.get_member(user_id)
            name = f"**{member.display_name}**" if member else f"*User-{user_id}*"
            
            # Tentukan Icon Rank
            rank_icon = medals[i] if i < 3 else f"`#{i+1}`"
            
            # Baris 1: Rank & Nama
            desc += f"{rank_icon} {name}\n"
            # Baris 2: Detail Stats (Indented)
            desc += f"└─ 🎙️ `{mins}m`  💬 `{chat_xp} XP`  ✨ `{total_xp} XP`\n"


        # ... (kode loop top users tetap sama) ...
        
        # --- [BARU] Bagian 4: Global Context ---
        # Hanya tampilkan jika server masuk ranking (rank > 0)
        if global_rank > 0:
            desc += "\n───────────────\n" # Separator halus
            desc += "**🌍 Global Context (Anonim)**\n"
            desc += f"• Peringkat server kamu: **#{global_rank}** dari {total_servers} server aktif\n"
            desc += f"• Total voice minggu ini: `{t_voice:,} menit`\n"
            
            # --- [BARU] Bagian 5: CTA Halus ---
            desc += "\n🔍 *Lihat ranking global lengkap dengan /global leaderboard*"


        embed = discord.Embed(
            title=f"📅 Weekly Leaderboard ({current_week})",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_footer(text="🌱 Perjalanan baru dimulai setiap Senin. Semua statistik disegarkan kembali.")
        
        # [DEBUG END] Matikan Stopwatch & Lapor
        duration = time.time() - start_time
        self.bot.logger.info("BENCHMARK", f"Weekly Leaderboard selesai dalam {duration:.4f} detik")

        # Kirim hasil dengan Safety Guard
        try:
            await interaction.followup.send(embed=embed)
        except (discord.NotFound, discord.HTTPException) as e:
            self.bot.logger.error("WEEKLY_CMD_FAIL", "Gagal kirim embed hasil", error_obj=e)

    # --- ADMIN CONFIG ---
    
    weekly_group = app_commands.Group(name="weekly", description="Konfigurasi Recap Mingguan")

    # --- GLOBAL LEADERBOARD (BARU) ---
    
    global_group = app_commands.Group(name="global", description="Statistik Global Lintas Server")

    @global_group.command(name="leaderboard", description="🌏 Top 10 Server Paling Aktif (Anonim).")
    async def global_lb(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        current_week = self.db.get_current_week_key()
        
        # 1. Ambil data agregat per guild
        query = """
            SELECT guild_id, SUM(weekly_voice_mins) as total_voice
            FROM weekly_stats 
            WHERE week_key = ? 
            GROUP BY guild_id 
            HAVING total_voice > 0
            ORDER BY total_voice DESC
            LIMIT 10
        """
        rows = await self.db.fetch_all(query, (current_week,))
        
        if not rows:
            return await interaction.followup.send("💤 Belum ada data global minggu ini.", ephemeral=True)
            
        # 2. Render Embed Anonim
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for i, row in enumerate(rows):
            # Cek apakah ini server tempat command dijalankan
            is_current_guild = (row['guild_id'] == interaction.guild_id)
            
            # Formatting Nama: "Server Kamu" atau "Server #XYZ"
            if is_current_guild:
                name = f"**__Server Ini ({interaction.guild.name})__** 📍"
            else:
                # Samarkan nama server lain (Privacy First)
                name = f"Server #{row['guild_id'] % 1000:03d}" 
            
            rank_icon = medals[i] if i < 3 else f"`#{i+1}`"
            desc += f"{rank_icon} {name} — 🎙️ `{row['total_voice']:,} min`\n"

        embed = discord.Embed(
            title=f"🌏 Global Leaderboard ({current_week})",
            description=f"10 server dengan percakapan paling hidup minggu ini:\n\n{desc}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Nama server lain disamarkan demi privasi.")
        
        await interaction.followup.send(embed=embed)    

    @weekly_group.command(name="enable", description="Aktifkan Auto-Recap setiap minggu baru.")
    @app_commands.checks.has_permissions(administrator=True)
    async def weekly_enable(self, interaction: discord.Interaction, channel: discord.TextChannel):
        current_week = self.db.get_current_week_key()
        
        await self.db.execute("""
            INSERT INTO weekly_config (guild_id, recap_channel_id, is_enabled, last_posted_week_key) 
            VALUES (?, ?, 1, ?)
            ON CONFLICT(guild_id) DO UPDATE SET 
                recap_channel_id = excluded.recap_channel_id,
                is_enabled = 1,
                last_posted_week_key = excluded.last_posted_week_key
        """, (interaction.guild.id, channel.id, current_week))
        
        await interaction.response.send_message(f"✅ Auto-Recap Mingguan aktif! Hasil akan dikirim ke {channel.mention}.")

    @weekly_group.command(name="disable", description="Matikan Auto-Recap.")
    @app_commands.checks.has_permissions(administrator=True)
    async def weekly_disable(self, interaction: discord.Interaction):
        await self.db.execute("UPDATE weekly_config SET is_enabled = 0 WHERE guild_id = ?", (interaction.guild.id,))
        await interaction.response.send_message("❌ Auto-Recap dimatikan.")
        
    @weekly_group.command(name="status", description="🔍 Cek kesehatan dan konfigurasi sistem rekap mingguan.")
    @app_commands.checks.has_permissions(administrator=True)
    async def weekly_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        current_week = self.db.get_current_week_key()
        
        # --- 1. AMBIL DATA CONFIG ---
        config = await self.db.fetch_one(
            "SELECT * FROM weekly_config WHERE guild_id = ?", 
            (guild.id,)
        )
        
        # --- 2. AMBIL DATA AKTIVITAS MINGGU INI ---
        # Hitung total partisipan
        stats_count_row = await self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM weekly_stats WHERE guild_id = ? AND week_key = ?",
            (guild.id, current_week)
        )
        participant_count = stats_count_row['cnt'] if stats_count_row else 0
        
        # Cari Top 1 sementara
        top_user_row = await self.db.fetch_one("""
            SELECT user_id, weekly_voice_mins, weekly_xp 
            FROM weekly_stats 
            WHERE guild_id = ? AND week_key = ? 
            ORDER BY weekly_voice_mins DESC LIMIT 1
        """, (guild.id, current_week))

        # --- 3. ANALISIS KESEHATAN (DIAGNOSA) ---
        status_emoji = "🔴"
        status_text = "Belum Setup"
        channel_info = "*(Belum diatur)*"
        last_posted = "*(Belum pernah)*"
        
        # Logic Pewarnaan & Diagnosa
        if config:
            # Cek Channel
            ch_id = config['recap_channel_id']
            recap_channel = guild.get_channel(ch_id)
            
            if config['is_enabled']:
                if recap_channel:
                    status_emoji = "🟢"
                    status_text = "AKTIF (Normal)"
                    channel_info = recap_channel.mention
                else:
                    status_emoji = "⚠️"
                    status_text = "ERROR (Channel Hilang)"
                    channel_info = f"❌ Invalid ID: {ch_id}"
            else:
                status_emoji = "🔴"
                status_text = "NON-AKTIF (Disabled)"
                channel_info = f"<#{ch_id}> (Tapi fitur mati)"
            
            if config['last_posted_week_key']:
                last_posted = config['last_posted_week_key']

        # --- 4. RENDER EMBED ---
        embed = discord.Embed(
            title=f"{status_emoji} Panel Status Mingguan",
            color=discord.Color.green() if status_text == "AKTIF (Normal)" else discord.Color.red()
        )
        
        # Blok A: Konfigurasi Sistem
        embed.add_field(name="⚙️ Konfigurasi", value=(
            f"**Status:** {status_text}\n"
            f"**Channel:** {channel_info}\n"
            f"**Loop:** Cek tiap 30 menit"
        ), inline=False)
        
        # Blok B: Informasi Waktu (Debug Key)
        embed.add_field(name="📅 Waktu & Checkpoint", value=(
            f"**Minggu Ini (Key):** `{current_week}`\n"
            f"**Terakhir Recap:** `{last_posted}`\n"
            f"⏰ Rekap dikirim otomatis saat minggu baru dimulai."
        ), inline=False)
        
        # Blok C: Preview Aktivitas (Live Data)
        if top_user_row:
            top_member = guild.get_member(top_user_row['user_id'])
            top_name = top_member.display_name if top_member else "Unknown User"
            top_stats = f"{top_name} ({top_user_row['weekly_voice_mins']}m / {top_user_row['weekly_xp']}XP)"
        else:
            top_stats = "*(Belum ada data)*"

        embed.add_field(name="📊 Preview Minggu Ini", value=(
            f"**Total Partisipan:** {participant_count} member\n"
            f"**Top 1 Saat Ini:** {top_stats}"
        ), inline=False)
        
        # Footer Tips
        if status_text.startswith("ERROR"):
            embed.set_footer(text="💡 Tips: Jalankan /weekly enable #channel lagi untuk perbaiki.")
        elif status_text.startswith("Belum"):
            embed.set_footer(text="💡 Tips: Jalankan /weekly enable #channel untuk mulai.")

        await interaction.followup.send(embed=embed)

    # --- AUTO RECAP TASK (The Killer Feature) ---
    
    
    @tasks.loop(minutes=30) 
    async def weekly_recap_loop(self):
        # Guard: Bot belum siap
        if not self.bot.is_ready(): return

        try:
            current_week = self.db.get_current_week_key()
            configs = await self.db.fetch_all("SELECT * FROM weekly_config WHERE is_enabled = 1")
            
            for conf in configs:
                # ISOLASI ERROR PER GUILD (Saran Senior Fix #1)
                try:
                    # Kita lempar logika berat ke fungsi baru (lihat FIX 3)
                    await self._process_single_guild_recap(conf, current_week)
                    
                except Exception as e:
                    # Jika Guild A error, Guild B TETAP JALAN
                    self.bot.logger.error(
                        "WEEKLY_GUILD_FAIL", 
                        f"Gagal rekap untuk guild {conf['guild_id']}", 
                        error_obj=e
                    )
                    
        except Exception as e:
            # Catch-all level teratas
            self.bot.logger.error("WEEKLY_FATAL", "Error di loop utama", error_obj=e)

    
    # METHOD BARU: Logika Spesifik per Guild
    async def _process_single_guild_recap(self, conf, current_week):
        guild_id = conf['guild_id']
        
        # 1. Cek Guild & Claim (Urutan Fix Sebelumnya)
        guild = self.bot.get_guild(guild_id)
        if not guild: return 

        if not await self.db.claim_weekly_recap(guild_id, current_week):
            return 

        channel = guild.get_channel(conf['recap_channel_id'])
        if not channel:
            # Auto-disable jika channel hilang
            await self.db.execute("UPDATE weekly_config SET is_enabled = 0 WHERE guild_id = ?", (guild_id,))
            await self.db.finish_weekly_recap(guild_id, current_week, "failed", "recap channel unavailable")
            return

        # 2. Persiapan Data Minggu Lalu
        prev_date = datetime.now(timezone.utc) - timedelta(days=7)
        prev_week_key = self.db.get_week_key_for_date(prev_date)
        
        prev_data = await self.db.fetch_all("""
            SELECT user_id, weekly_voice_mins, weekly_xp 
            FROM weekly_stats 
            WHERE guild_id = ? AND week_key = ?
            ORDER BY weekly_voice_mins DESC
            LIMIT 10
        """, (guild_id, prev_week_key))

        # Jika tidak ada data minggu lalu, stop
        if not prev_data:
            await self.db.finish_weekly_recap(guild_id, current_week, "empty")
            return

        # 3. FIX VARIABEL SCOPE & LOGIKA (Saran Senior)
        desc = ""
        top_3_emojis = ["🥇", "🥈", "🥉"] # Definisi DI AWAL
        common_path_cache = {}

        # 4. Loop Data Member
        for i, row in enumerate(prev_data):
            user_id = row['user_id']
            m = guild.get_member(user_id)
            
            # Fallback nama yang aman
            name = m.display_name if m else f"User-{user_id}"
            
            # Logic Prefix Rank
            rank_prefix = top_3_emojis[i] if i < 3 else f"**#{i+1}**"
            desc += f"{rank_prefix} **{name}** — 🎙️ `{row['weekly_voice_mins']}m` ✨ `{row['weekly_xp']}XP`\n"

            # Logic Badge (Voice Order)
            if row['weekly_voice_mins'] > 60:
                await self.db.unlock_badge(user_id, guild_id, "badge_voice_order")

            # Logic Badge (Common Path) - FIX DB NONE TYPE
            if user_id not in common_path_cache:
                query_common = """
                    SELECT COUNT(DISTINCT week_key) as weeks_count
                    FROM weekly_stats 
                    WHERE user_id = ? AND guild_id = ? AND weekly_voice_mins >= 60
                """
                res_common = await self.db.fetch_one(query_common, (user_id, guild_id))
                
                # [FIX] Handle jika fetch_one return None
                weeks_active = res_common['weeks_count'] if res_common else 0
                common_path_cache[user_id] = weeks_active
            
            if common_path_cache[user_id] >= 4:
                if await self.db.unlock_badge(user_id, guild_id, "badge_common_path"):
                    await self.db.unlock_title(user_id, guild_id, "title_fellow_path")

        # 5. Global Context
        g_rank, g_total = await self.db.get_guild_weekly_rank(guild_id, prev_week_key)
        
        header_desc = ""
        if g_rank > 0:
            total_voice = sum(r['weekly_voice_mins'] for r in prev_data)
            header_desc += "**🌍 Global Context**\n"
            header_desc += f"• Peringkat server: **#{g_rank}** dari {g_total}\n"
            header_desc += f"• Total voice (Top 10): `{total_voice:,} menit`\n"
            header_desc += "───────────────\n\n"

        # Gabungkan Header + List User
        final_desc = header_desc + desc

        # 6. Kirim Embed (FIX NETWORK CALL)
        embed = discord.Embed(
            title=f"📅 REKAP MINGGUAN ({prev_week_key})",
            description=f"Inilah pahlawan keaktifan minggu lalu!\n\n{final_desc}",
            color=discord.Color.fuchsia()
        )
        embed.set_footer(text="Statistik telah di-reset. Gas lagi!")

        try:
            await channel.send(embed=embed)
            # At-least-once: a process loss after Discord accepts the send but before
            # this state update can cause a retry after the pending lease expires.
            await self.db.finish_weekly_recap(guild_id, current_week, "posted")
        except Exception as e:
            self.bot.logger.error("WEEKLY_SEND_FAIL", f"Gagal kirim ke {channel.id}", error_obj=e)
            await self.db.finish_weekly_recap(guild_id, current_week, "failed", str(e))

    # [FIX SENIOR 3] Tambahkan Error Handler Khusus Loop
    # GANTI method ini sepenuhnya
    @weekly_recap_loop.error
    async def weekly_recap_error(self, error):
        if self.bot.is_shutting_down:
            return
        
        self.bot.logger.error("WEEKLY_LOOP_CRASH", "Loop mati", error_obj=error)

        await asyncio.sleep(10)

        if self.bot.is_closed():
            return

        if not self.weekly_recap_loop.is_running():
            try:
                self.weekly_recap_loop.start()
            except RuntimeError as e:
                self.bot.logger.error("WEEKLY_RESTART_FAIL", "Gagal restart loop", error_obj=e)

    @weekly_recap_loop.before_loop
    async def before_recap(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(WeeklyStats(bot, bot.db))
