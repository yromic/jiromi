# cogs/admin_config.py
import discord
from discord import app_commands
from discord.ext import commands
from utils.views import ExecutorView 

class ResetConfirmView(ExecutorView):
    def __init__(self, db, guild_id, author_id):
        super().__init__(author_id=author_id, timeout=30)
        self.db = db
        self.guild_id = guild_id
        self.value = None
        self._finished = False 

    @discord.ui.button(label="YA, HAPUS SEMUA XP", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
        
        count = await self.db.reset_guild_xp(self.guild_id)
        
        embed = discord.Embed(
            description=f"✅ **RESET BERHASIL.**\nXP dan Level dari {count} member telah dikembalikan ke 0.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        
        self.value = True
        self.stop()

    @discord.ui.button(label="BATAL", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
            
        await interaction.response.edit_message(
            content="❌ **Operasi Dibatalkan.** Data aman.", 
            embed=None, 
            view=None
        )
        self.value = False
        self.stop()


class FilterResetView(discord.ui.View):
    def __init__(self, db, guild_id, author_id): 
        super().__init__(timeout=30)
        self.db = db
        self.guild_id = guild_id
        self.author_id = author_id 
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("⛔ Ini bukan menu konfirmasimu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="YA, RESET FILTER", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.db.reset_guild_filters(self.guild_id)
        button.disabled = True
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(content="✅ **Semua filter telah di-reset.**", view=self, embed=None)
        self.stop()

    @discord.ui.button(label="BATAL", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Dibatalkan.", view=self, embed=None)
        self.stop()
        
        
class AdminConfig(commands.GroupCog, name="xp"):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        super().__init__()

    role_group = app_commands.Group(name="role", description="Atur role yang diizinkan/dilarang")

    @role_group.command(name="allow", description="Izinkan role tertentu untuk mulai mendapatkan XP.") 
    @app_commands.describe(role="Role yang akan dimasukkan ke Whitelist")
    @app_commands.checks.has_permissions(administrator=True)
    async def role_allow(self, interaction, role: discord.Role):

        await self.db.remove_filter(interaction.guild_id, role.id)
        
        await self.db.add_filter(interaction.guild_id, role.id, 'role', 'allow')
        
        await interaction.response.send_message(f"✅ Role {role.mention} sekarang masuk dalam **Whitelist**.")

    @role_group.command(name="disallow", description="Larang role tertentu agar tidak bisa mendapatkan XP.")
    @app_commands.checks.has_permissions(administrator=True)
    async def role_disallow(self, interaction: discord.Interaction, role: discord.Role):

        await self.db.remove_filter(interaction.guild_id, role.id)
        
        await self.db.add_filter(interaction.guild_id, role.id, 'role', 'exclude')
        
        await interaction.response.send_message(f"🚫 Role {role.mention} sekarang masuk dalam **Blacklist**.")

    reward_group = app_commands.Group(name="reward", description="Atur hadiah role per level")

    @reward_group.command(name="add", description="Tambah hadiah role untuk level tertentu.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_reward(self, interaction: discord.Interaction, level: int, role: discord.Role):
        bot_member = interaction.guild.me
        
        if role.position >= bot_member.top_role.position:
            embed = discord.Embed(
                title=" ❌  Gagal Menambahkan Reward",
                description=(
                    f"Role {role.mention} posisinya **lebih tinggi** atau setara dengan role bot.\n"
                    "Discord melarang bot memberikan role yang lebih tinggi darinya.\n\n"
                    "👉 **Solusi:** Geser role bot ke paling atas di Server Settings > Roles."
                ),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if role.is_default() or role.managed:
            await interaction.response.send_message(" ❌  Tidak bisa menjadikan role bawaan/integrasi sebagai reward.", ephemeral=True)
            return

        await self.db.add_reward(interaction.guild_id, level, role.id)
        await interaction.response.send_message(f" 🎁  Berhasil! Member level **{level}** akan mendapatkan role {role.mention}.")

    @reward_group.command(name="list", description="Lihat daftar role reward yang sudah diset.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_rewards(self, interaction: discord.Interaction):

        rewards = await self.db.fetch_all(
            "SELECT level_required, role_id FROM rewards WHERE guild_id = ? ORDER BY level_required ASC",
            (interaction.guild_id,)
        )

        if not rewards:
            embed = discord.Embed(
                description=" 📭  Belum ada Level Reward yang dikonfigurasi di server ini.",
                color=discord.Color.light_gray()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        description = ""
        bot_top_role = interaction.guild.me.top_role

        for row in rewards:
            level = row['level_required']
            role_id = row['role_id']
            role = interaction.guild.get_role(role_id)

            if role:

                status_icon = "✅" if role.position < bot_top_role.position else "⚠️"
                role_text = role.mention
            else:

                status_icon = "❌"
                role_text = f"*(Role Terhapus: {role_id})*"

            description += f"**Level {level}** ➜ {role_text} {status_icon}\n"

        embed = discord.Embed(
            title=f" 🎁  Level Rewards: {interaction.guild.name}",
            description=description,
            color=discord.Color.blue()
        )
        
        embed.set_footer(text="✅ = Aman | ⚠️ = Role ketinggian (Bot tidak bisa kasih) | ❌ = Role hilang")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup" , description="Konfigurasi dasar Jiromi untuk server ini.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_config(self, interaction: discord.Interaction, 
                           channel_announcement: discord.TextChannel,
                           voice_xp: int = 10, chat_xp: int = 5):
        await self.db.update_config(interaction.guild_id, channel_announcement.id, voice_xp, chat_xp)
        await interaction.response.send_message("⚙️ Konfigurasi server telah diperbarui!")

    @app_commands.command(name="announcement", description="Atur seberapa sering bot memberikan pengumuman level up.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Quiet (Tanpa Notifikasi)", value="quiet"),
        app_commands.Choice(name="Balanced (Hanya saat dapat Role)", value="balanced"),
        app_commands.Choice(name="Loud (Setiap naik level)", value="loud")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_announcement_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await self.db.update_announcement_mode(interaction.guild_id, mode.value)
        
        descriptions = {
            "quiet": "Bot akan bekerja dalam diam tanpa notifikasi level up.",
            "balanced": "Bot hanya akan mengirim pengumuman jika member mendapatkan Role Reward.",
            "loud": "Bot akan merayakan setiap kenaikan level member di channel pengumuman."
        }
        await interaction.response.send_message(f"✅ Mode pengumuman diubah ke **{mode.name}**.\n*{descriptions[mode.value]}*")

    @app_commands.command(name="status", description="Lihat status kesehatan dan konfigurasi sistem XP.")
    @app_commands.checks.has_permissions(administrator=True)
    async def show_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        bot_member = guild.me

        config = await self.db.get_guild_config(guild.id)
        filters = await self.db.get_filters(guild.id)
        rewards = await self.db.fetch_all(
            "SELECT level_required, role_id FROM rewards WHERE guild_id = ?",
            (guild.id,)
        )

        safe = warning = missing = 0
        for row in rewards:
            role = guild.get_role(row['role_id'])
            if not role:
                missing += 1
            elif role.position >= bot_member.top_role.position:
                warning += 1
            else:
                safe += 1

        def format_mentions(data_list, type_filter, category, fmt_pattern):
            ids = [f['target_id'] for f in data_list if f['type'] == type_filter and f['category'] == category]
            if not ids:
                return "*(Tidak ada / Semua Boleh)*" if category == 'allow' else "*(Tidak ada)*"
            return ", ".join([fmt_pattern.format(id) for id in ids])

        role_allow_str = format_mentions(filters, 'role', 'allow', "<@&{}>")
        role_deny_str = format_mentions(filters, 'role', 'exclude', "<@&{}>")
        
        chan_allow_str = format_mentions(filters, 'channel', 'allow', "<#{}>")
        chan_deny_str = format_mentions(filters, 'channel', 'exclude', "<#{}>")

        chat_xp = config['chat_xp_val']
        voice_xp = config['voice_xp_val']
        xp_active = (chat_xp > 0 or voice_xp > 0)
        mode = config['announcement_mode'].capitalize()

        embed = discord.Embed(
            title=" 🩺  Status Kesehatan Jiromi",
            color=discord.Color.green() if xp_active else discord.Color.red()
        )

        embed.add_field(name="XP System", value="✅ Aktif" if xp_active else "❌ Mati", inline=True)
        embed.add_field(name="Notifikasi", value=f"📢 **{mode}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(name="💬 Chat Rate", value=f"`{chat_xp} XP` / pesan", inline=True)
        embed.add_field(name="🎙️ Voice Rate", value=f"`{voice_xp} XP` / menit", inline=True)
        embed.add_field(name="👥 Min Voice", value=f"`{config['min_members_voice']} orang`", inline=True)

        embed.add_field(name="🎭 Role Whitelist (Khusus)", value=role_allow_str, inline=True)
        embed.add_field(name="🚫 Role Blacklist (Dilarang)", value=role_deny_str, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False) # Spacer

        embed.add_field(name="✅ Channel Whitelist", value=chan_allow_str, inline=True)
        embed.add_field(name="⛔ Channel Blacklist", value=chan_deny_str, inline=True)
        
        reward_stats = (
            f"Total Config: **{len(rewards)}**\n"
            f"✅ Aman: {safe} | ⚠️ Bahaya: {warning} | ❌ Error: {missing}"
        )
        embed.add_field(name="🎁 Reward Health", value=reward_stats, inline=False)

        if not xp_active:
            embed.set_footer(text="⚠️ XP non-aktif. Gunakan /setup atau /xp setup.")
        elif warning > 0 or missing > 0:
            embed.set_footer(text="⚠️ Isu pada Reward. Cek /xp reward list.")
        else:
            embed.set_footer(text="🟢 Sistem berjalan optimal.")

        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "⛔ **Akses Ditolak:** Perintah konfigurasi XP hanya untuk Administrator."
            
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            print(f"❌ Error pada XP Config: {error}")

    
    @app_commands.command(name="reset", description="⚠️ BAHAYA: Reset XP semua member di server ini ke 0.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_xp_all(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="⚠️ PERINGATAN KERAS: ZONA BAHAYA",
            description=(
                f"Kamu akan mereset **SEMUA DATA XP & LEVEL** di server **{interaction.guild.name}**.\n\n"
                "🔻 **Konsekuensi:**\n"
                "1. Semua member akan kembali ke Level 0.\n"
                "2. Semua XP chat & voice akan dihapus.\n"
                "3. Role reward tidak otomatis dicabut (harus manual/tunggu update).\n"
                "4. **Tindakan ini TIDAK BISA DIBATALKAN.**\n\n"
                "Apakah kamu yakin 100%?"
            ),
            color=discord.Color.red()
        )
        
        view = ResetConfirmView(self.db, interaction.guild_id, interaction.user.id)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
    
    @app_commands.command(name="reset_user", description="Reset XP & Level satu member spesifik ke 0.")
    @app_commands.describe(member="Member yang akan di-reset XP-nya")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_user_xp_cmd(self, interaction: discord.Interaction, member: discord.Member):
        if member.bot:
            await interaction.response.send_message("❌ Bot tidak memiliki XP.", ephemeral=True)
            return

        affected_rows = await self.db.reset_user_xp(interaction.guild_id, member.id)

        if affected_rows > 0:
            await interaction.response.send_message(
                f"✅ **Berhasil!** XP dan Level milik {member.mention} telah di-reset ke 0.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ **Data tidak ditemukan.** {member.mention} belum memiliki history XP di server ini.",
                ephemeral=True
            )
            
    @role_group.command(name="remove", description="Hapus role dari Whitelist/Blacklist (Jadikan Netral).")
    @app_commands.checks.has_permissions(administrator=True)
    async def role_remove(self, interaction: discord.Interaction, role: discord.Role):

        await self.db.remove_filter(interaction.guild_id, role.id)
        
        await interaction.response.send_message(
            f"✅ Aturan untuk Role {role.mention} telah dihapus. Sekarang role ini **Netral**."
        )
        
    filter_group = app_commands.Group(name="filter", description="Manajemen Filter Global")

    @filter_group.command(name="reset", description="⚠️ Hapus SEMUA aturan Whitelist/Blacklist.")
    @app_commands.checks.has_permissions(administrator=True)
    async def filter_reset_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚠️ Konfirmasi Reset Filter",
            description="Ini akan menghapus semua konfigurasi **Role & Channel** (Whitelist/Blacklist).\nSemua akan kembali ke default.",
            color=discord.Color.red()
        )
        
        view = FilterResetView(self.db, interaction.guild_id, interaction.user.id)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    channel_group = app_commands.Group(name="channel", description="Atur whitelist/blacklist channel untuk XP.")

    @channel_group.command(name="allow", description="✅ Whitelist: Hanya channel ini yang bisa dapat XP.")
    @app_commands.describe(channel="Channel yang ingin diizinkan (Text/Voice)")
    @app_commands.checks.has_permissions(administrator=True)
    async def channel_allow(self, interaction, channel: discord.abc.GuildChannel):

        await self.db.remove_filter(interaction.guild_id, channel.id) 
        
        await self.db.add_filter(interaction.guild_id, channel.id, 'channel', 'allow')
        
        await interaction.response.send_message(
            f"✅ **Whitelist:** XP sekarang **AKTIF** di {channel.mention}.\n"
            f"*(Catatan: Jika ini whitelist pertama, channel lain otomatis mati)*"
        )

    @channel_group.command(name="disallow", description="⛔ Blacklist: Matikan XP di channel ini.")
    @app_commands.describe(channel="Channel yang ingin dimatikan XP-nya")
    @app_commands.checks.has_permissions(administrator=True)
    async def channel_disallow(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):

        await self.db.remove_filter(interaction.guild_id, channel.id)
        
        await self.db.add_filter(interaction.guild_id, channel.id, 'channel', 'exclude')
        
        await interaction.response.send_message(f"⛔ **Blacklist:** XP telah **DIMATIKAN** di {channel.mention}.")

    @channel_group.command(name="remove", description="🗑️ Hapus filter: Kembalikan channel ke status Netral.")
    @app_commands.describe(channel="Channel yang akan dihapus aturannya")
    @app_commands.checks.has_permissions(administrator=True)
    async def channel_remove(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):

        await self.db.remove_filter(interaction.guild_id, channel.id)
        
        await interaction.response.send_message(
            f"🗑️ Aturan XP di {channel.mention} telah dihapus (Status: **Netral**)."
        )

    @app_commands.command(name="refresh_cache", description="[Admin] Hapus cache error agar bot mencoba memberi role lagi.")
    @app_commands.checks.has_permissions(administrator=True)
    async def refresh_role_cache(self, interaction: discord.Interaction):

        self.failed_roles_cache.clear()
        await interaction.response.send_message("✅ Cache error telah dibersihkan. Bot akan mencoba memberikan role yang tertunda pada aktivitas member berikutnya.")

async def setup(bot):
    """Fungsi inisialisasi global untuk discord.py agar bisa memuat Cog ini."""
    await bot.add_cog(AdminConfig(bot, bot.db))