# cogs/profile.py

import discord
from discord import app_commands
from discord.ext import commands
from utils.math_utils import xp_for_next_level
from utils.badge_data import BADGE_ICONS, BADGE_META, TITLE_META

class Profile(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    # Mapping ID Database -> Emoji Visual
    BADGE_ICONS = {
    # Badge lama
    "badge_echo_mark": "<:speaker_jiromi:1467342396986757212>",
    "badge_sound_sigil": "<:shield_jiromi:1467342758921506838>",
    "badge_unbroken_seal": "<:fire_jiromi:1467342251674964090>",
    "badge_voice_order": "<:sword_jiromi:1467342441542586410>",
    "badge_resonant_path": "<:star_jiromi:1467342479710883924>",

    # Badge baru
    "badge_quiet_anchor": "<:anchor_jiromi:1467342312358281404>",
    "badge_steady_flame": "<:candle_jiromi:1467342528520126536>",
    "badge_common_path": "<:track_jiromi:1467342573374017667>",
    "badge_still_here": "<:tree_jiromi:1467342354632413392>",
    }

    @app_commands.command(name="rank", description="🏁 Social Snapshot: Lihat posisimu di antara member lain.")
    @app_commands.describe(member="🏁 Melihat posisimu saat ini di antara anggota server.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        # [FIX 1] Lakukan Defer DI AWAL.
        # Ini memberitahu Discord: "Sabar ya, lagi loading".
        # Bot punya waktu 15 menit, bukan cuma 3 detik.
        await interaction.response.defer()

        member = member or interaction.user
        
        # 1. Ambil Context Ranking
        # Proses ini berat karena membaca seluruh database user di guild.
        # Untungnya kita sudah defer, jadi aman.
        rank_pos, total_members, above, below = await self._get_rank_context(interaction.guild.id, member.id)
        
        if not rank_pos:
            # [FIX 2] Gunakan followup.send karena sudah di-defer
            return await interaction.followup.send("🍂 Belum ada jejak langkah di server ini.", ephemeral=True)

        # 2. Ambil Data User (XP/Level)
        user_data = await self.db.get_user_data(member.id, interaction.guild.id)
        
        # 3. Ambil Title (Safe Render Logic yang baru)
        active_title, _, _ = await self.db.get_user_gamification_profile(member.id, interaction.guild.id)
        
        # Logic Title (Menggunakan META yang baru kita fix tadi)
        # Import TITLE_META perlu ada di file ini (dari utils.badge_data)
        title_str = ""
        if active_title:
            if active_title in TITLE_META:
                title_name = TITLE_META[active_title]['name']
            else:
                title_name = active_title.replace("title_", "").replace("_", " ").title()
            title_str = f" — {title_name}"

        # 4. Render Embed (Warna Slate/Abu kebiruan)
        embed = discord.Embed(color=discord.Color.from_rgb(96, 125, 139)) 
        
        embed.set_author(name=f"Rank di {interaction.guild.name}", icon_url=member.display_avatar.url)
        embed.title = f"{member.display_name}{title_str}"

        # BLOK 1: Posisi
        embed.add_field(
            name="📊 Posisi", 
            value=f"#**{rank_pos}** dari {total_members} member", 
            inline=True
        )

        # BLOK 2: Status Singkat
        voice_str = f"{user_data['total_voice_mins']}m"
        if user_data['total_voice_mins'] > 60:
            h = user_data['total_voice_mins'] // 60
            m = user_data['total_voice_mins'] % 60
            voice_str = f"{h}j {m}m"

        embed.add_field(
            name="✨ Status", 
            value=f"Level {user_data['level']}\n🎙️ {voice_str} voice", 
            inline=True
        )

        # BLOK 3: Konteks Sosial (Tetangga)
        # Tetangga Atas
        if above:
            above_lines = [f"#{rank_pos - (i+1)} <@{r['user_id']}>" for i, r in enumerate(reversed(above))]
            above_str = "\n".join(above_lines)
        else:
            above_str = "*Puncak Server*"

        # Tetangga Bawah
        if below:
            below_lines = [f"#{rank_pos + (i+1)} <@{r['user_id']}>" for i, r in enumerate(below)]
            below_str = "\n".join(below_lines)
        else:
            below_str = "*Dasar Server*"
        
        embed.add_field(name="⬆️ Di Atasmu", value=above_str, inline=True)
        embed.add_field(name="⬇️ Di Bawahmu", value=below_str, inline=True)

        embed.set_footer(text="Snapshot saat ini • Tidak mencerminkan seluruh perjalanan • Cek /profile")
        
        # [FIX 3] Kirim menggunakan followup, bukan response.send_message
        await interaction.followup.send(embed=embed)

    # --- TITLE SYSTEM COMMANDS ---
    
    title_group = app_commands.Group(name="title", description="Kelola julukan profilmu.")

    @app_commands.command(name="profile", description="🌱 Personal Diary: Melihat catatan perjalanan dan pencapaianmu.")
    @app_commands.describe(member="🌱 Catatan perjalanan pribadimu di komunitas ini.")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user

        # 1. AMBIL DATA DULU (Database Call Harus Paling Atas)
        # Kita butuh data active_title sebelum memprosesnya
        user_data = await self.db.get_user_data(member.id, interaction.guild.id)
        active_title, badges, _ = await self.db.get_user_gamification_profile(member.id, interaction.guild.id)

        # 2. PROSES LOGIKA TITLE (Safe Render)
        title_text = "Warga" # Default value

        if active_title:
            # Coba ambil dari META pusat
            if active_title in TITLE_META:
                title_text = TITLE_META[active_title]['name']
            else:
                # Fallback: Format ID jadi Tulisan Rapi
                title_text = active_title.replace("title_", "").replace("_", " ").title()

        # 3. Hitung Durasi Perjalanan (Journey Age)
        if member.joined_at:
            delta = discord.utils.utcnow() - member.joined_at
            days_joined = delta.days
            journey_str = f"Bersama selama {days_joined} hari"
        else:
            journey_str = "Baru saja bergabung"

        # 4. MULAI BIKIN EMBED
        embed = discord.Embed(color=discord.Color.from_rgb(129, 199, 132))
        
        # Header: Personal
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.title = f"🌱 Perjalanan {member.display_name}"
        
        # [PENTING] Gunakan variabel title_text yang sudah diproses di atas (Poin 2)
        embed.description = f"**{title_text}**" 

        # BLOK 1: Journey (Waktu)
        embed.add_field(name="🕰️ Waktu", value=journey_str, inline=False)

        # BLOK 2: Kehadiran
        v_mins = user_data['total_voice_mins']
        if v_mins < 60: voice_desc = "Pendengar baru"
        elif v_mins < 600: voice_desc = "Aktif bersuara"
        else: voice_desc = "Suara familiar komunitas"
        
        chat_count = user_data['xp'] // 5 
        if chat_count < 50: chat_desc = "Menyapa sesekali"
        elif chat_count < 500: chat_desc = "Aktif berdiskusi"
        else: chat_desc = "Aktif merangkai percakapan"

        embed.add_field(
            name="Kehadiran", 
            value=f"🎙️ Voice: {voice_desc} ({v_mins}m)\n💬 Chat: {chat_desc}", 
            inline=False
        )

        # BLOK 3: Milestone & Badge
        if badges:
            BADGE_NAMES = {
                "badge_echo_mark": "Echo Mark (Voice I)",
                "badge_sound_sigil": "Sound Sigil (Voice II)",
                "badge_unbroken_seal": "Unbroken Seal (Streak)",
                "badge_voice_order": "Voice of Order (Weekly)",
                "badge_resonant_path": "Resonant Path (Level 10)",
                "badge_quiet_anchor": "Quiet Anchor (3000m)",
                "badge_steady_flame": "Steady Flame (30 Days)",
                "badge_common_path": "Common Path (4 Weeks)",
                "badge_still_here": "Still Here (1 Year)"
            }
            
            badge_list = []
            for b in badges[:5]: 
                icon = self.BADGE_ICONS.get(b, "🏅")
                name = BADGE_NAMES.get(b, b.replace("_", " ").title())
                badge_list.append(f"{icon} **{name}**")
            
            milestone_str = "\n".join(badge_list)
        else:
            milestone_str = "*(Belum ada lencana yang tersemat)*"
            
        embed.add_field(name="🏅 Pencapaian", value=milestone_str, inline=False)

        # BLOK 4: Progress Bar
        from utils.math_utils import xp_for_next_level
        lvl = user_data['level']
        xp = user_data['xp']
        floor = xp_for_next_level(lvl - 1) if lvl > 0 else 0
        ceil = xp_for_next_level(lvl)
        current = xp - floor
        needed = ceil - floor
        
        ratio = current / needed if needed > 0 else 1
        filled = int(ratio * 10)
        bar = "▓" * filled + "░" * (10 - filled)
        
        embed.add_field(
            name=f"✨ Level {lvl}", 
            value=f"`{bar}`\nMelangkah menuju babak berikutnya...", 
            inline=False
        )

        embed.set_footer(text="Perjalanan ini bersifat personal • Tidak untuk dibandingkan")

        await interaction.response.send_message(embed=embed)

    @title_group.command(name="list", description="Lihat koleksi Title yang sudah kamu buka.")
    async def title_list(self, interaction: discord.Interaction):
        _, _, titles_owned = await self.db.get_user_gamification_profile(interaction.user.id, interaction.guild.id)
        
        if not titles_owned:
            return await interaction.response.send_message("📭 Kamu belum memiliki Title apapun. Teruslah aktif!", ephemeral=True)
            
        desc = "Gunakan `/title select` untuk memakainya.\n\n"
        for t_id in titles_owned:
            # [FIX] Ambil dari TITLE_META
            meta = TITLE_META.get(t_id)
            if meta:
                desc += f"🏷️ **{meta['name']}** — *{meta['desc']}*\n"
            else:
                # Fallback aman jika title lama
                clean_name = t_id.replace("title_", "").replace("_", " ").title()
                desc += f"🏷️ **{clean_name}**\n"
            
        embed = discord.Embed(title="🎒 Koleksi Title", description=desc, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @title_group.command(name="select", description="Pasang Title agar muncul di sebelah namamu.")
    async def title_select(self, interaction: discord.Interaction):
        # 1. Ambil data title user
        _, _, titles_owned = await self.db.get_user_gamification_profile(interaction.user.id, interaction.guild.id)
        
        if not titles_owned:
             return await interaction.response.send_message("❌ Kamu tidak punya Title untuk dipilih.", ephemeral=True)
             
        # 2. Tampilkan Dropdown Menu
        view = TitleView(self.db, titles_owned, self.TITLE_NAMES)
        await interaction.response.send_message("pilih identitas barumu:", view=view, ephemeral=True)

    @app_commands.command(name="leaderboard", description="🏆 Hall of Fame: Top 50 member paling aktif (Voice & XP).")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer() # Defer karena query mungkin agak berat

        # 1. Ambil Top 50 Data (XP Descending)
        # Kita ambil total_voice_mins juga sesuai request
        query = """
            SELECT user_id, xp, level, total_voice_mins 
            FROM users 
            WHERE guild_id = ? 
            ORDER BY xp DESC 
            LIMIT 50
        """
        rows = await self.db.fetch_all(query, (interaction.guild.id,))

        if not rows:
            return await interaction.followup.send("🍂 Belum ada data aktivitas di server ini.")

        # 2. Proses Data (Resolve Nama User)
        # Kita lakukan resolve nama di sini agar pagination (View) tidak perlu fetch user lagi (lemot)
        processed_data = []
        for row in rows:
            member = interaction.guild.get_member(row['user_id'])
            # Fallback jika member sudah keluar server
            name = member.display_name if member else f"User-{row['user_id']}"
            
            processed_data.append({
                "name": name,
                "level": row['level'],
                "xp": row['xp'],
                "total_voice_mins": row['total_voice_mins']
            })

        # 3. Tampilkan View Pagination
        view = LeaderboardView(processed_data, interaction.user.id)
        embed = view.create_embed()
        
        await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="level", description="🧭 Melihat progres level perjalanan.")
    @app_commands.describe(user="Lihat level member lain")
    async def level(self, interaction: discord.Interaction, user: discord.Member | None = None): # [FIX 4] Type Hint Modern
        target = user or interaction.user
        is_self = (target.id == interaction.user.id)

        user_data = await self.db.get_user_data(target.id, interaction.guild.id)
        lvl = user_data['level']
        xp = user_data['xp']
        
        # Hitung target
        next_limit = xp_for_next_level(lvl)
        
        # [FIX 1] Cegah nilai negatif dengan max(0, ...)
        remaining = max(0, next_limit - xp)

        # Helper format angka (30.000)
        def fmt(n): return f"{n:,}".replace(",", ".")

        # [FIX 2] Cukup cek lvl == 0 (Defensive: abaikan jika ada sisa XP nyasar)
        if lvl == 0:
            if is_self:
                # [FIX 3] Konsistensi tone reflektif
                msg = "🧭 Level 0\n\nPerjalanan baru saja dimulai.\nMasih ada jalan di depan."
            else:
                msg = f"🧭 Level 0 — {target.display_name}\n\nPerjalanan baru saja dimulai."
        else:
            if is_self:
                msg = (
                    f"🧭 Level {lvl}\n\n"
                    f"Kau telah menempuh {fmt(xp)} langkah.\n"
                    f"Masih tersisa {fmt(remaining)} langkah lagi.\n\n"
                    "Masih ada jalan di depan."
                )
            else:
                msg = (
                    f"🧭 Level {lvl} — {target.display_name}\n\n"
                    f"{fmt(xp)} langkah telah ditempuh.\n"
                    f"Tersisa {fmt(remaining)} langkah lagi."
                )

        await interaction.response.send_message(content=msg, ephemeral=is_self)

        

    # Helper untuk menghitung Ranking & Neighbors
    async def _get_rank_context(self, guild_id, user_id):
        # Ambil semua user di guild, urutkan by XP tertinggi
        # (Untuk skala ribuan member, ini masih sangat cepat di SQLite)
        all_users = await self.db.fetch_all(
            "SELECT user_id, xp, level FROM users WHERE guild_id = ? ORDER BY xp DESC",
            (guild_id,)
        )
        
        # Cari index user kita
        rank = -1
        user_data = None
        
        for i, row in enumerate(all_users):
            if row['user_id'] == user_id:
                rank = i + 1 # Rank mulai dari 1
                user_data = row
                break
        
        if rank == -1: return None, None, [], []

        # Ambil tetangga (Neighbors)
        # Di atas kita (index lebih kecil)
        start_above = max(0, rank - 4) # Ambil 3 orang di atas
        above_rows = all_users[start_above : rank-1]
        
        # Di bawah kita (index lebih besar)
        below_rows = all_users[rank : rank + 3] # Ambil 3 orang di bawah

        return rank, len(all_users), above_rows, below_rows

class TitleSelect(discord.ui.Select):
    def __init__(self, db, titles_owned): # Hapus parameter title_map
        self.db = db
        
        options = []
        options.append(discord.SelectOption(label="❌ Lepas Title", value="none", description="Kembali ke nama polosan."))
        
        for t_id in titles_owned:
            # [FIX] Ambil dari TITLE_META global
            meta = TITLE_META.get(t_id)
            if meta:
                label_name = meta['name']
                desc = meta['desc']
            else:
                label_name = t_id.replace("title_", "").replace("_", " ").title()
                desc = "Title Legacy"

            options.append(discord.SelectOption(label=label_name, value=t_id, emoji="🏷️", description=desc[:100]))

        super().__init__(placeholder="Pilih Title aktifmu...", min_values=1, max_values=1, options=options)

# Update View-nya juga agar tidak perlu passing map lagi
class TitleView(discord.ui.View):
    def __init__(self, db, titles_owned): # Hapus parameter title_map
        super().__init__(timeout=60)
        self.add_item(TitleSelect(db, titles_owned))

class LeaderboardView(discord.ui.View):
    def __init__(self, data, interaction_user_id):
        super().__init__(timeout=60)
        self.data = data
        self.per_page = 10
        self.current_page = 0
        self.total_pages = (len(data) - 1) // self.per_page + 1
        self.interaction_user_id = interaction_user_id
        
        # [FIX RED 1] Simpan referensi pesan buat edit saat timeout
        self.message = None 
        self.update_buttons()

    def update_buttons(self):
        # [FIX ORANGE 1] Logic Tombol yang Aman (Tidak bergantung urutan index)
        # Kita iterasi children dan cek callback-nya, atau set state langsung di button
        
        # Tombol Prev (kita tahu ini tombol pertama yg kita define, tapi biar aman kita set logicnya)
        # Di sini kita akses item secara spesifik lewat atribut custom class kalau mau,
        # tapi cara paling simpel dan robust adalah loop children:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "⬅️ Sebelumnya":
                    child.disabled = (self.current_page == 0)
                elif child.label == "Selanjutnya ➡️":
                    child.disabled = (self.current_page == self.total_pages - 1)

    def _truncate_text(self, text, max_len):
        """[FIX ORANGE 2] Helper untuk potong nama dengan aman."""
        if len(text) <= max_len:
            return text
        return text[:max_len-1] + "…"

    def _format_number(self, num):
        """[FIX ORANGE 3] Helper format angka besar biar tabel gak geser."""
        s = f"{num:,}"
        if len(s) > 8: # Jika lebih dari 99,999,999 (8 digit + koma)
            # Format jadi 1.2M
            return f"{num/1000000:.1f}M"
        return s

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_data = self.data[start:end]

        table_str = ""
        
        for i, row in enumerate(page_data):
            rank = start + i + 1
            
            # [FIX VISUAL] Nama & Angka diamankan
            name = self._truncate_text(row['name'], 10) 
            xp_str = self._format_number(row['xp'])
            
            lvl = row['level']
            voice = row['total_voice_mins']
            
            # Format Voice compact
            if voice < 60:
                voice_str = f"{voice}m"
            else:
                h = voice // 60
                m = voice % 60
                voice_str = f"{h}h{m}m"

            # Icon Rank
            if rank == 1: r_icon = "🥇"
            elif rank == 2: r_icon = "🥈"
            elif rank == 3: r_icon = "🥉"
            else: r_icon = f"#{rank:<2}"

            # Format Tabel Monospace (Rata Kiri)
            # Spasi diatur ketat agar lurus di HP
            table_str += f"{r_icon} `{name:<10}` `Lv.{lvl:<3}` `🎙️{voice_str:<6}` `✨{xp_str:<6}`\n"

        embed = discord.Embed(
            title="🏆 Server Leaderboard",
            description=f"Top Member Berdasarkan Aktivitas\n\n{table_str}",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Halaman {self.current_page + 1}/{self.total_pages} • Total {len(self.data)} Member")
        return embed

    async def on_timeout(self):
        """[FIX RED 1] Handler saat waktu habis."""
        # Matikan semua tombol
        for child in self.children:
            child.disabled = True
        
        # Update pesan jika masih ada
        if self.message:
            try:
                # [FIX VISUAL] Kasih tau user kalau menu expired
                embed = self.create_embed()
                embed.set_footer(text="⌛ Menu kadaluwarsa. Ketik /leaderboard lagi.")
                await self.message.edit(embed=embed, view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

    @discord.ui.button(label="⬅️ Sebelumnya", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # [FIX GREEN 3] Executor Lock (Udah bener, pertahankan)
        if interaction.user.id != self.interaction_user_id:
            return await interaction.response.send_message("⛔ Ini bukan menumu.", ephemeral=True)
            
        self.current_page -= 1
        self.update_buttons()
        
        # [FIX RED 2] Guard Clause Interaction
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Selanjutnya ➡️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction_user_id:
            return await interaction.response.send_message("⛔ Ini bukan menumu.", ephemeral=True)

        self.current_page += 1
        self.update_buttons()
        
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

async def setup(bot):
    await bot.add_cog(Profile(bot, bot.db))
