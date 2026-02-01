# cogs/profile.py

import discord
from discord import app_commands
from discord.ext import commands
from utils.math_utils import xp_for_next_level

class Profile(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    # Mapping ID Database -> Emoji Visual
    BADGE_ICONS = {
        "badge_echo_mark": "📢",      
        "badge_sound_sigil": "🛡️",    
        "badge_unbroken_seal": "🔥",  
        "badge_voice_order": "⚔️",    
        "badge_resonant_path": "✨"  
    }
    
    TITLE_NAMES = {
        "title_echo_bearer": "Echo Bearer",       # Awal
        "title_resonant_knight": "Resonant Knight", # Leveling
        "title_unbroken": "Unbroken"              # Streak 7 Hari
    }

    @app_commands.command(name="rank", description="🏁 Social Snapshot: Lihat posisimu di antara member lain.")
    @app_commands.describe(member="🏁 Melihat posisimu saat ini di antara anggota server.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        
        # 1. Ambil Context Ranking
        rank_pos, total_members, above, below = await self._get_rank_context(interaction.guild.id, member.id)
        
        if not rank_pos:
            return await interaction.response.send_message("🍂 Belum ada jejak langkah di server ini.", ephemeral=True)

        # 2. Ambil Data User (XP/Level)
        user_data = await self.db.get_user_data(member.id, interaction.guild.id)
        
        # 3. Warna Netral (Biru Abu-abu / Slate) - Sesuai style "Social Snapshot"
        embed = discord.Embed(color=discord.Color.from_rgb(96, 125, 139)) 
        
        # Header: Identitas Ringkas
        active_title, _, _ = await self.db.get_user_gamification_profile(member.id, interaction.guild.id)
        title_str = f" — {self.TITLE_NAMES.get(active_title, active_title)}" if active_title else ""
        
        embed.set_author(name=f"Rank di {interaction.guild.name}", icon_url=member.display_avatar.url)
        embed.title = f"{member.display_name}{title_str}"

        # BLOK 1: Posisi
        embed.add_field(
            name="📊 Posisi", 
            value=f"#**{rank_pos}** dari {total_members} member", 
            inline=True
        )

        # BLOK 2: Status Singkat
        # Voice menit dikonversi ke jam jika > 60 agar lebih rapi
        voice_str = f"{user_data['total_voice_mins']}m"
        if user_data['total_voice_mins'] > 60:
            voice_str = f"{user_data['total_voice_mins'] // 60}j {user_data['total_voice_mins'] % 60}m"

        embed.add_field(
            name="✨ Status", 
            value=f"Level {user_data['level']}\n🎙️ {voice_str} voice", 
            inline=True
        )

        # BLOK 3: Konteks Sosial (Tetangga) - BERSIH TANPA DUPLIKASI
        
        # Tetangga Atas
        if above:
            # Menggunakan reversed agar urutannya: Rank 5, Rank 6 -> KITA (Rank 7)
            # Format: #Rank @User
            above_lines = [f"#{rank_pos - (i+1)} <@{r['user_id']}>" for i, r in enumerate(reversed(above))]
            above_str = "\n".join(above_lines)
        else:
            above_str = "*Puncak Server*"

        # Tetangga Bawah
        if below:
            # Format: #Rank @User
            below_lines = [f"#{rank_pos + (i+1)} <@{r['user_id']}>" for i, r in enumerate(below)]
            below_str = "\n".join(below_lines)
        else:
            below_str = "*Dasar Server*"
        
        embed.add_field(name="⬆️ Di Atasmu", value=above_str, inline=True)
        embed.add_field(name="⬇️ Di Bawahmu", value=below_str, inline=True)

        # Footer: Filosofi
        embed.set_footer(text="Snapshot saat ini • Tidak mencerminkan seluruh perjalanan • Cek /profile")
        
        await interaction.response.send_message(embed=embed)

    # --- TITLE SYSTEM COMMANDS ---
    
    title_group = app_commands.Group(name="title", description="Kelola julukan profilmu.")

    @app_commands.command(name="profile", description="🌱 Personal Diary: Melihat catatan perjalanan dan pencapaianmu.")
    @app_commands.describe(member="🌱 Catatan perjalanan pribadimu di komunitas ini.")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        
        # 1. Ambil Data Lengkap
        user_data = await self.db.get_user_data(member.id, interaction.guild.id)
        active_title, badges, _ = await self.db.get_user_gamification_profile(member.id, interaction.guild.id)
        
        # 2. Hitung Durasi Perjalanan (Journey Age)
        # Menggunakan member.joined_at dari Discord API
        if member.joined_at:
            delta = discord.utils.utcnow() - member.joined_at
            days_joined = delta.days
            journey_str = f"Bersama selama {days_joined} hari"
        else:
            journey_str = "Baru saja bergabung"

        # 3. Warna Hangat/Alam (Sage Green)
        embed = discord.Embed(color=discord.Color.from_rgb(129, 199, 132))
        
        # Header: Personal
        title_text = self.TITLE_NAMES.get(active_title, active_title) if active_title else "Warga"
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.title = f"🌱 Perjalanan {member.display_name}"
        embed.description = f"**{title_text}**" # Active Title jadi highlight

        # BLOK 1: Journey (Waktu)
        embed.add_field(name="🕰️ Waktu", value=journey_str, inline=False)

        # BLOK 2: Kehadiran (Deskriptif, bukan angka mentah)
        # Logika deskriptif sederhana
        v_mins = user_data['total_voice_mins']
        if v_mins < 60: voice_desc = "Pendengar baru"
        elif v_mins < 600: voice_desc = "Aktif bersuara"
        else: voice_desc = "Suara familiar komunitas"
        
        # Chat XP check (asumsi rata-rata 5xp per chat)
        chat_count = user_data['xp'] // 5 
        if chat_count < 50: chat_desc = "Menyapa sesekali"
        elif chat_count < 500: chat_desc = "Aktif berdiskusi"
        else: chat_desc = "Aktif merangkai percakapan"

        embed.add_field(
            name="Kehadiran", 
            value=f"🎙️ Voice: {voice_desc} ({v_mins}m)\n💬 Chat: {chat_desc}", 
            inline=False
        )

        # BLOK 3: Milestone & Badge (Limit 5)
        if badges:
            # Render badge dengan nama aslinya biar lebih 'bercerita'
            # Kita mapping manual ID ke Nama Cantik
            BADGE_NAMES = {
                "badge_echo_mark": "Echo Mark (Voice I)",
                "badge_sound_sigil": "Sound Sigil (Voice II)",
                "badge_unbroken_seal": "Unbroken Seal (Streak)",
                "badge_voice_order": "Voice of Order (Weekly)",
                "badge_resonant_path": "Resonant Path (Level 10)"
            }
            
            badge_list = []
            for b in badges[:5]: # Max 5
                icon = self.BADGE_ICONS.get(b, "🏅")
                name = BADGE_NAMES.get(b, b.replace("_", " ").title())
                badge_list.append(f"{icon} **{name}**")
            
            milestone_str = "\n".join(badge_list)
        else:
            milestone_str = "*(Belum ada lencana yang tersemat)*"
            
        embed.add_field(name="🏅 Pencapaian", value=milestone_str, inline=False)

        # BLOK 4: Progress (Visual Bar)
        # Kita pakai logic bar lama tapi dipercantik
        from utils.math_utils import xp_for_next_level
        lvl = user_data['level']
        xp = user_data['xp']
        floor = xp_for_next_level(lvl - 1) if lvl > 0 else 0
        ceil = xp_for_next_level(lvl)
        current = xp - floor
        needed = ceil - floor
        
        ratio = current / needed if needed > 0 else 1
        filled = int(ratio * 10)
        # Bar Ghibli style: Kotak solid & shade
        bar = "▓" * filled + "░" * (10 - filled)
        
        embed.add_field(
            name=f"✨ Level {lvl}", 
            value=f"`{bar}`\nMelangkah menuju babak berikutnya...", 
            inline=False
        )

        # Footer: Filosofi
        embed.set_footer(text="Perjalanan ini bersifat personal • Tidak untuk dibandingkan")

        await interaction.response.send_message(embed=embed)

    @title_group.command(name="list", description="Lihat koleksi Title yang sudah kamu buka.")
    async def title_list(self, interaction: discord.Interaction):
        _, _, titles_owned = await self.db.get_user_gamification_profile(interaction.user.id, interaction.guild.id)
        
        if not titles_owned:
            return await interaction.response.send_message("📭 Kamu belum memiliki Title apapun. Teruslah aktif!", ephemeral=True)
            
        desc = "Gunakan `/title select` untuk memakainya.\n\n"
        for t_id in titles_owned:
            name = self.TITLE_NAMES.get(t_id, t_id)
            desc += f"🏷️ **{name}**\n"
            
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

    @app_commands.command(name="leaderboard", description="Melihat 5 pilar utama komunitas (Top 5).")
    async def leaderboard(self, interaction: discord.Interaction):
        top_members = await self.db.fetch_all(
            "SELECT user_id, xp, level FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT 5",
            (interaction.guild.id,)
        )
        
        if not top_members:
            return await interaction.response.send_message("Belum ada sejarah yang tercatat di server ini.", ephemeral=True)

        description = ""
        for i, row in enumerate(top_members, 1):
            member = interaction.guild.get_member(row['user_id'])
            name = member.mention if member else f"Warga Lama ({row['user_id']})"
            description += f"**{i}. {name}** — Level {row['level']} ({row['xp']} XP)\n"

        embed = discord.Embed(
            title="✨ Pilar Komunitas (Top 5)",
            description=description,
            color=discord.Color.gold()
        )
        embed.set_footer(text="Bukan tentang siapa yang tercepat, tapi siapa yang tetap ada.")
        
        await interaction.response.send_message(embed=embed)

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
    def __init__(self, db, titles_owned, title_map):
        self.db = db
        
        options = []
        # Opsi 1: Copot Title (None)
        options.append(discord.SelectOption(label="❌ Lepas Title", value="none", description="Kembali ke nama polosan."))
        
        # Opsi 2: Title yang dimiliki user
        for t_id in titles_owned:
            # Ambil nama keren dari dictionary, atau pakai ID mentah kalau gak ada di dict
            label_name = title_map.get(t_id, t_id)
            options.append(discord.SelectOption(label=label_name, value=t_id, emoji="🏷️"))

        super().__init__(placeholder="Pilih Title aktifmu...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Value 'none' artinya copot title
        new_title = self.values[0] if self.values[0] != "none" else None
        
        await self.db.set_active_title(interaction.user.id, interaction.guild.id, new_title)
        
        # Feedback
        msg = f"✅ Title profilmu diubah menjadi: **{self.values[0]}**" if new_title else "✅ Title dilepas."
        await interaction.response.edit_message(content=msg, view=None)

class TitleView(discord.ui.View):
    def __init__(self, db, titles_owned, title_map):
        super().__init__(timeout=60)
        self.add_item(TitleSelect(db, titles_owned, title_map))

async def setup(bot):
    await bot.add_cog(Profile(bot, bot.db))
