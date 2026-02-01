# cogs/leveling.py
import discord
from discord.ext import commands, tasks
import time
from utils.badge_data import BADGE_ICONS, BADGE_META

class Leveling(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.mute_tracker = {}
        self.failed_roles_cache = {} # [FIX] Ubah jadi Dict untuk simpan timestamp
        self.CACHE_TTL = 3600 # [FIX] TTL 1 Jam (3600 detik)
        self.voice_heartbeat.start()

    def cog_unload(self):
        self.voice_heartbeat.cancel()

    # [FIX] Gantikan method voice_heartbeat yang lama dengan dua method ini:

    
    @tasks.loop(minutes=1.0)
    async def voice_heartbeat(self):
        """
        Loop utama dengan Exception Handling Global.
        Jika terjadi error, loop akan mencatat log tapi TIDAK AKAN MATI.
        """
        # 1. Guard: Pastikan bot sudah siap sebelum loop jalan
        if not self.bot.is_ready():
            return

        try:
            for guild in self.bot.guilds:
                # 2. Isolasi Error per Guild
                # Kita bungkus proses tiap guild agar error di Server A 
                # tidak menghentikan XP di Server B.
                try:
                    await self._process_guild_voice(guild)
                except Exception as e:
                    # Log error spesifik guild, tapi loop lanjut ke guild berikutnya
                    self.bot.logger.error(
                        "VOICE_GUILD_FAIL", 
                        f"Gagal memproses voice untuk guild {guild.name}", 
                        error_obj=e,
                        guild_id=guild.id
                    )
                    
        except Exception as e:
            # 3. Catch-All Global
            # Jika error terjadi di level teratas (misal self.bot.guilds bermasalah)
            # Loop akan selamat dan mencoba lagi menit depan.
            self.bot.logger.error(
                "VOICE_LOOP_CRASH", 
                "Critical error pada voice heartbeat loop", 
                error_obj=e
            )

    

    async def _process_guild_voice(self, guild):
        """
        Helper method untuk memproses satu guild.
        Memisahkan logic agar kode lebih bersih dan terisolasi.
        """
        # Ambil config (Bisa error DB Timeout disini, makanya perlu try-except di atas)
        config = await self.db.get_guild_config(guild.id)
        if not config:
            return

        # Iterasi Voice Channel
        for vc in guild.voice_channels:
            # Filter member aktif
            # [Safe Access] Kita gunakan list comprehension yang aman
            active_members = []
            for m in vc.members:
                if m.bot: continue
                
                # [FIX SENIOR] Guard attribute access untuk mencegah crash
                # Jika member disconnect tepat saat loop jalan, m.voice bisa None
                if not m.voice: continue 
                if m.voice.self_deaf: continue
                
                active_members.append(m)

            if len(active_members) < config['min_members_voice']:
                continue

            # Proses XP per Member
            for member in active_members:
                try:
                    # Cek eligibility (DB Call)
                    if not await self.db.is_eligible(member, vc):
                        continue

                    await self.process_voice_xp(member, config)
                    
                except Exception as e:
                    # [Fail-Soft per Member]
                    # Jika 1 member error, member lain di channel yang sama TETAP dapat XP
                    self.bot.logger.error(
                        "VOICE_MEMBER_FAIL",
                        f"Gagal add XP untuk {member.name}",
                        error_obj=e,
                        guild_id=guild.id
                    )


    async def process_voice_xp(self, member, config):
        key = (member.guild.id, member.id)
        is_muted = member.voice.self_mute or member.voice.mute

        if is_muted:
            self.mute_tracker[key] = self.mute_tracker.get(key, 0) + 1
            if self.mute_tracker[key] > 5:
                return
        else:
            self.mute_tracker[key] = 0
            
        minutes = 1 
        xp_gain = minutes * config['voice_xp_val']

        result = await self.db.add_voice_time(
            member.id,
            member.guild.id,
            minutes,
            config['voice_xp_val']
        )
        
        # [HOOK] Update Weekly Stats
        await self.db.update_weekly_stats(
            guild_id=member.guild.id, 
            user_id=member.id, 
            xp_add=xp_gain, 
            voice_mins_add=minutes,
            chat_xp_add=0 
        )

        self.bot.loop.create_task(self._try_send_global_intro(member))

        if result['new_level'] > result['old_level']:
            await self.handle_level_up(member, result['old_level'], result['new_level'])

        # 1. Update Streak & Ambil Data Terbaru
        streak_now = await self.db.update_voice_streak(member.id, member.guild.id)
        user_data = await self.db.get_user_data(member.id, member.guild.id) 
        total_mins = user_data['total_voice_mins']
        old_total_mins = total_mins - minutes

        # [HELPER BARU] Fungsi Notifikasi "Jiromi Style"
        # (Fungsi send_achiev_msg yang lama SUDAH DIHAPUS karena tidak dipakai)
        async def send_badge_notification(badge_id, extra=None):
            # Cek Config Channel
            if not config['announce_channel_id']: return
            channel = member.guild.get_channel(config['announce_channel_id'])
            if not channel: return
            if not channel.permissions_for(member.guild.me).send_messages: return

            # Ambil Data dari Source of Truth
            icon = BADGE_ICONS.get(badge_id, "🏅")
            meta = BADGE_META.get(badge_id, {"name": "Unknown", "short_desc": "Badge baru."})

            # Rakit Pesan (Bisikan, bukan Teriak)
            lines = [
                f"{icon} **{meta['name']}**",
                f"{member.mention} — {meta['short_desc']}" 
            ]

            if "detail" in meta:
                lines.append(f"*{meta['detail']}*") 
            
            if extra:
                lines.append(f"\n{extra}") 

            try:
                await channel.send("\n".join(lines))
            except Exception as e:
                
                self.bot.logger.error(
                    "BADGE_NOTIFY_FAIL",
                    f"Gagal kirim notif badge {badge_id}",
                    error_obj=e
                )


        if total_mins >= 1:
            if await self.db.unlock_badge(member.id, member.guild.id, "badge_echo_mark"):
                await self.db.unlock_title(member.id, member.guild.id, "title_echo_bearer")
                await send_badge_notification("badge_echo_mark", extra="Mendapatkan Title: **[Echo Bearer]**")

        if total_mins >= 1000:
            if await self.db.unlock_badge(member.id, member.guild.id, "badge_sound_sigil"):
                await send_badge_notification("badge_sound_sigil")

        if streak_now >= 7:
            if await self.db.unlock_badge(member.id, member.guild.id, "badge_unbroken_seal"):
                await self.db.unlock_title(member.id, member.guild.id, "title_unbroken")
                await send_badge_notification("badge_unbroken_seal", extra="Mendapatkan Title: **[Unbroken]**")

        if old_total_mins < 3000 <= total_mins:
            if await self.db.unlock_badge(member.id, member.guild.id, "badge_quiet_anchor"):
                await self.db.unlock_title(member.id, member.guild.id, "title_waykeeper")
                await send_badge_notification("badge_quiet_anchor", extra="Mendapatkan Title: **[Waykeeper]**")

        old_streak = streak_now - 1
        if old_streak < 30 <= streak_now: 
            if await self.db.unlock_badge(member.id, member.guild.id, "badge_steady_flame"):
                await self.db.unlock_title(member.id, member.guild.id, "title_the_steady")
                await send_badge_notification("badge_steady_flame", extra="Mendapatkan Title: **[The Steady]**")

        self.bot.stats_buffer['voice_xp_events'] += 1
        self.bot.stats_buffer['voice_minutes'] += minutes


    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        if not await self.db.is_eligible(message.author, message.channel):
            return

        user_data = await self.db.get_user_data(
            message.author.id,
            message.guild.id
        )

        if time.time() - user_data['last_chat_ts'] < 10:
            return

        if len(message.content) < 8:
            return

        config = await self.db.get_guild_config(message.guild.id)
        result = await self.db.add_chat_xp(
            message.author.id,
            message.guild.id,
            config['chat_xp_val']
        )
        
        # [HOOK] Update Weekly Stats
        await self.db.update_weekly_stats(
            guild_id=message.guild.id,
            user_id=message.author.id,
            xp_add=config['chat_xp_val'],
            voice_mins_add=0, # Voice nol karena ini chat
            chat_xp_add=config['chat_xp_val'] # [PENTING] Isi kolom chat
        )

        self.bot.loop.create_task(self._try_send_global_intro(message.author))

        if result['new_level'] > result['old_level']:
            # [FIX] Pass old_level juga
            await self.handle_level_up(message.author, result['old_level'], result['new_level'])
            
        self.bot.stats_buffer['chat_xp_events'] += 1

    # Di dalam cogs/leveling.py -> handle_level_up()

    async def handle_level_up(self, member, old_level, new_level):
        config = await self.db.get_guild_config(member.guild.id)
        mode = config['announcement_mode'] if config else 'balanced' 

        reward_role = await self.check_role_rewards(member, new_level) 
        
        if old_level < 10 <= new_level:
            if await self.db.unlock_badge(member.id, member.guild.id, "badge_resonant_path"):
                 await self.db.unlock_title(member.id, member.guild.id, "title_resonant_knight")

        if mode == "quiet":
            return # Tidak ada pengumuman sama sekali

        if mode == "balanced":
            # Hanya umumkan jika ada role baru yang didapat dari check_role_rewards di atas
            if reward_role:
                await self.handle_announcement(member, new_level, reward_role)
            return

        if mode == "loud":
            # Umumkan setiap naik level, baik ada role maupun tidak
            await self.handle_announcement(member, new_level, reward_role)

    async def check_role_rewards(self, member, level):
        rewards = await self.db.fetch_all(
            "SELECT level_required, role_id FROM rewards "
            "WHERE guild_id = ? ORDER BY level_required ASC",
            (member.guild.id,)
        )
        
        latest_role = None
        for row in rewards:
            if level >= row['level_required']:
                role_id = row['role_id']
                role = member.guild.get_role(role_id)
                
                if not role: 
                    continue
                
                cache_key = (member.guild.id, member.id, role_id)
                if cache_key in self.failed_roles_cache:
                    last_failure_time = self.failed_roles_cache[cache_key]
                    
                    if time.time() - last_failure_time < self.CACHE_TTL:
                        continue
                    else:
                        # Jika sudah lebih dari 1 jam, hapus dari cache & coba lagi (Retry)
                        del self.failed_roles_cache[cache_key]

                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Presence Reward")
                        latest_role = role
                        # Jika sukses, hapus dari cache kegagalan (kalau ada)
                        self.failed_roles_cache.discard((member.guild.id, member.id, role_id))
                        
                    except discord.Forbidden:
                        self.failed_roles_cache[(member.guild.id, member.id, role_id)] = time.time()
                        
                        self.bot.logger.error(
                            "ROLE_GRANT_FAIL",
                            f"Izin ditolak memberi role {role.name}. Retry dalam 1 jam.",
                            guild_id=member.guild.id,
                            user_id=member.id
                        )
                    except Exception as e:
                        print(f" ❌  Error tak terduga saat memberi reward: {e}")

        return latest_role

    async def handle_announcement(self, member, level, new_role):
        config = await self.db.get_guild_config(member.guild.id)
        if not config or not config['announce_channel_id']:
            return

        channel = member.guild.get_channel(config['announce_channel_id'])
        if not channel:
            return
        
        # Cek Permission Bot di channel tersebut
        # (Penting agar tidak error jika bot tidak bisa kirim embed)
        perms = channel.permissions_for(member.guild.me)
        if not perms.send_messages:
            return

        # --- LOGIKA PESAN SPESIAL ---
        
        # KONDISI 1: DAPAT ROLE (Spesial / Mewah)
        # Ini akan jalan di mode 'Balanced' DAN 'Loud' saat user dapat role.
        if new_role:
            embed = discord.Embed(
                title="🏆 PENCAPAIAN BARU TERBUKA!",
                description=(
                    f"Selamat {member.mention}! Dedikasimu luar biasa.\n"
                    f"Kamu telah mencapai **Level {level}** dan mendapatkan gelar baru:\n\n"
                    f"# 🎖️ {new_role.mention}" 
                ),
                color=discord.Color.gold() # Warna Emas agar terasa premium
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Teruslah aktif untuk hadiah berikutnya!")
            
            try:
                # Kirim dengan mention user di luar embed agar notif masuk
                await channel.send(content=f"🎉 {member.mention}", embed=embed)
            except discord.Forbidden:
                # Fallback jika bot tidak punya izin embed
                await channel.send(f"🏆 Selamat {member.mention}! Kamu naik ke **Level {level}** dan mendapat role **{new_role.name}**!")

        # KONDISI 2: LEVEL UP BIASA (Standar)
        # Ini hanya jalan di mode 'Loud' saat user naik level tapi TIDAK dapat role.
        else:
            # Pesan teks simple agar tidak spam visual
            msg = f"🆙 **Level Up!** Selamat {member.mention}, kamu baru saja naik ke **Level {level}**."
            await channel.send(msg)

    @voice_heartbeat.before_loop
    async def before_voice_heartbeat(self):
        await self.bot.wait_until_ready()

    
    async def _try_send_global_intro(self, member):
        """
        Logika tunggal untuk mengirim pesan perkenalan global.
        Rules: 1x seumur hidup, via DM, Fail Silent.
        """
        # 1. Cek Database (Cepat & Ringan)
        if not await self.db.should_send_global_intro(member.id):
            return

        # 2. Siapkan Pesan (Sesuai Blueprint Senior)
        embed = discord.Embed(
            title="🌱 Aku Jiromi",
            description=(
                f"Hai {member.name},\n"
                "aku Jiromi.\n"
                "Aku hadir di berbagai komunitas untuk menemani perjalanan kecil yang sering luput dari perhatian —\n\n"
                "obrolan singkat, waktu bersama di voice, dan kehadiran yang konsisten.\n"
                "Tidak ada keharusan untuk bersaing.\n\n"
                "Tidak ada tuntutan untuk aktif.\n\n"
                "Setiap langkah punya ritmenya sendiri."
            ),
            color=discord.Color.from_rgb(240, 240, 240) # Warna netral/lembut (sesuai selera)
        )
        # Footer context (Penting agar user tau trigger-nya)
        embed.set_footer(text=f"Pesan ini muncul karena aktivitas pertamamu di {member.guild.name}")

        # 3. Kirim DM (Fail Silent)
        try:
            await member.send(embed=embed)
            
            # 4. Tandai di DB (Hanya jika DM sukses terkirim)
            await self.db.mark_global_intro_seen(member.id)
            
            # Log audit kecil (Opsional, buat debug admin aja)
            self.bot.logger.info("GLOBAL_INTRO", f"Sent global intro to {member.name} ({member.id})")
            
        except discord.Forbidden:
            # User tutup DM -> Tandai SUDAH dilihat agar bot tidak mencoba terus-menerus
            # (Sesuai prinsip: Fail Silent & No Retry Spam)
            await self.db.mark_global_intro_seen(member.id)
        except Exception:
            pass # Error lain abaikan saja

    # [FIX FINAL] Global Task Error Handler
    @voice_heartbeat.error
    async def voice_heartbeat_error(self, error):
        self.bot.logger.error(
            "VOICE_LOOP_CRASH", 
            "Voice XP loop mati total (Critical)", 
            error_obj=error
        )


    
# Ganti fungsi setup di bagian paling bawah cogs/leveling.py
async def setup(bot):
    # bot.db sudah diinisialisasi di main.py, jadi kita bisa langsung memakainya
    await bot.add_cog(Leveling(bot, bot.db))
