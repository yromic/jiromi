# cogs/profile.py

import discord
from discord import app_commands
from discord.ext import commands
from utils.math_utils import xp_for_next_level

class Profile(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    @app_commands.command(name="rank", description="Lihat progres kehadiran dan kontribusimu di komunitas.")
    @app_commands.describe(member="Member yang ingin dilihat profilnya (kosongkan untuk diri sendiri)")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user

        # 1. Ambil data
        user_data = await self.db.get_user_data(member.id, interaction.guild.id)
        total_xp = user_data['xp']
        level = user_data['level']
        voice_mins = user_data['total_voice_mins']

        # 2. Hitung Range Level Ini (Local Progress)
        # Ambang batas XP untuk level saat ini (Floor)
        xp_floor = xp_for_next_level(level - 1) if level > 0 else 0
        # Ambang batas XP untuk level berikutnya (Ceiling)
        xp_ceiling = xp_for_next_level(level)

        # XP yang sudah dikumpulkan HANYA di level ini
        xp_current_progress = total_xp - xp_floor
        # Total XP yang dibutuhkan untuk menyelesaikan level ini
        xp_needed_for_level = xp_ceiling - xp_floor

        # 3. Hitung Persentase (Local)
        if xp_needed_for_level > 0:
            ratio = xp_current_progress / xp_needed_for_level
        else:
            ratio = 1.0 # Max level logic (jika ada)

        percentage_bar = min(int(ratio * 10), 10)
        percentage_text = int(ratio * 100)

        # 4. Visual Bar
        bar = "█" * percentage_bar + "░" * (10 - percentage_bar)

        # 5. Buat Embed dengan UX yang BENAR
        embed = discord.Embed(
            title=f"Profil Kehadiran: {member.display_name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Info Utama
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        # Tampilkan Total XP terpisah agar user tetap bangga dengan angka besarnya
        embed.add_field(name="Total XP (Lifetime)", value=f"{total_xp:,}", inline=True)
        embed.add_field(name="Waktu Voice", value=f"{voice_mins} menit", inline=True)
        
        # LOGIC BARU: Label angka sesuai dengan Bar
        # Contoh: 1,500 / 12,000 XP (bukan 8000/19000)
        embed.add_field(
            name=f"Progres Menuju Level {level + 1}",
            value=(
                f"`{bar}` **{percentage_text}%**\n"
                f"📈 **{xp_current_progress:,} / {xp_needed_for_level:,} XP** (Current Level)\n"
                f"🎯 Kurang **{xp_needed_for_level - xp_current_progress:,} XP** lagi"
            ),
            inline=False
        )
        
        embed.set_footer(text="Kehadiranmu sangat berarti bagi kami.")

        await interaction.response.send_message(embed=embed)

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

async def setup(bot):
    await bot.add_cog(Profile(bot, bot.db))
