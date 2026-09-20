# cogs/admin_config.py
import discord
from discord import app_commands
from discord.ext import commands
from utils.views import ExecutorView 
from utils.interaction_responses import send_interaction_error

class ResetConfirmView(ExecutorView):
    def __init__(self, db, guild_id, author_id):
        super().__init__(author_id=author_id, timeout=30)
        self.db = db
        self.guild_id = guild_id
        self.value = None
        self._finished = False 

    @discord.ui.button(label="Reset XP", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
        
        count = await self.db.reset_guild_xp(self.guild_id)
        
        embed = discord.Embed(
            description=f"**Reset berhasil.**\nXP dan level {count} member telah dikembalikan ke 0. Total menit voice dan riwayat mingguan tetap tersimpan.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        
        self.value = True
        self.stop()

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
            
        await interaction.response.edit_message(
            content="Operasi dibatalkan. Data tidak berubah.",
            embed=None, 
            view=None
        )
        self.value = False
        self.stop()


class ResetUserConfirmView(ExecutorView):
    def __init__(self, db, guild_id, author_id, member: discord.Member):
        super().__init__(author_id=author_id, timeout=30)
        self.db = db
        self.guild_id = guild_id
        self.member = member
        self._finished = False

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished:
            return
        self._finished = True
        affected_rows = await self.db.reset_user_xp(self.guild_id, self.member.id)
        if affected_rows:
            content = (
                f"XP dan level {self.member.mention} sudah direset ke 0. "
                "Menit voice, riwayat mingguan, dan role reward tetap tersimpan."
            )
        else:
            content = f"Data XP {self.member.mention} belum ada, jadi tidak ada yang direset."
        await interaction.response.edit_message(content=content, embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished:
            return
        self._finished = True
        await interaction.response.edit_message(content="Reset dibatalkan. Tidak ada data yang diubah.", embed=None, view=None)
        self.stop()


class FilterResetView(ExecutorView):
    def __init__(self, db, guild_id, author_id): 
        super().__init__(author_id=author_id, timeout=30)
        self.db = db
        self.guild_id = guild_id

    @discord.ui.button(label="Reset filter", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.db.reset_guild_filters(self.guild_id)
        button.disabled = True
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(content="Semua filter telah direset.", view=self, embed=None)
        self.stop()

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Reset filter dibatalkan.", view=self, embed=None)
        self.stop()
        
        
class AdminConfig(commands.GroupCog, name="xp"):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        
        self.failed_roles_cache = {} 
        self.reward_roles_cache = {} 
        
        super().__init__()

    role_group = app_commands.Group(name="role", description="Atur role yang diizinkan/dilarang")

    @role_group.command(name="allow", description="Izinkan role tertentu untuk mulai mendapatkan XP.") 
    @app_commands.describe(role="Role yang akan dimasukkan ke Whitelist")
    @app_commands.checks.has_permissions(administrator=True)
    async def role_allow(self, interaction, role: discord.Role):

        await self.db.remove_filter(interaction.guild_id, role.id)
        
        await self.db.add_filter(interaction.guild_id, role.id, 'role', 'allow')
        
        await interaction.response.send_message(f"Role {role.mention} sekarang masuk dalam **Whitelist**.")

    @role_group.command(name="disallow", description="Larang role tertentu agar tidak bisa mendapatkan XP.")
    @app_commands.checks.has_permissions(administrator=True)
    async def role_disallow(self, interaction: discord.Interaction, role: discord.Role):

        await self.db.remove_filter(interaction.guild_id, role.id)
        
        await self.db.add_filter(interaction.guild_id, role.id, 'role', 'exclude')
        
        await interaction.response.send_message(f"Role {role.mention} sekarang masuk dalam **Blacklist**.")

    reward_group = app_commands.Group(name="reward", description="Atur hadiah role per level")

    @reward_group.command(name="add", description="Tambah hadiah role untuk level 1 sampai 2.147.483.647.")
    @app_commands.describe(level="Level positif, dari 1 sampai 2.147.483.647", role="Role yang diberikan saat level tercapai")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_reward(self, interaction: discord.Interaction, level: int, role: discord.Role):
        bot_member = interaction.guild.me

        if level < 1 or level > 2_147_483_647:
            await interaction.response.send_message("Level reward harus dari 1 sampai 2.147.483.647.", ephemeral=True)
            return
        
        if role.position >= bot_member.top_role.position:
            embed = discord.Embed(
                title="Reward tidak dapat ditambahkan",
                description=(
                    f"Role {role.mention} posisinya **lebih tinggi** atau setara dengan role bot.\n"
                    "Discord melarang bot memberikan role yang lebih tinggi darinya.\n\n"
                    "Pindahkan role bot ke atas role reward di Server Settings > Roles."
                ),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if role.is_default() or role.managed:
            await interaction.response.send_message("Role bawaan server atau role integrasi tidak dapat dijadikan reward.", ephemeral=True)
            return

        await self.db.add_reward(interaction.guild_id, level, role.id)
        await interaction.response.send_message(f"Member yang mencapai level **{level}** akan mendapat role {role.mention}.")

    @reward_group.command(name="list", description="Lihat daftar role reward yang sudah diset.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_rewards(self, interaction: discord.Interaction):

        rewards = await self.db.fetch_all(
            "SELECT level_required, role_id FROM rewards WHERE guild_id = ? ORDER BY level_required ASC",
            (interaction.guild_id,)
        )

        if not rewards:
            embed = discord.Embed(
                description="Belum ada level reward yang dikonfigurasi di server ini.",
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

                status = "Aman" if role.position < bot_top_role.position else "Perlu diperiksa: posisi role terlalu tinggi"
                role_text = role.mention
            else:

                status = "Role tidak ditemukan"
                role_text = f"*(Role Terhapus: {role_id})*"

            description += f"**Level {level}** — {role_text}\nStatus: {status}\n"

        embed = discord.Embed(
            title=f"Level reward: {interaction.guild.name}",
            description=description,
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup" , description="Pengaturan cepat untuk admin yang sudah tahu channel dan nilai XP.")
    @app_commands.describe(
        channel_announcement="Channel untuk pengumuman level up",
        voice_xp="XP tiap menit voice (0 untuk menonaktifkan)",
        chat_xp="XP tiap pesan (0 untuk menonaktifkan)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_config(self, interaction: discord.Interaction, 
                           channel_announcement: discord.TextChannel,
                           voice_xp: app_commands.Range[int, 0, 2147483647] = 10,
                           chat_xp: app_commands.Range[int, 0, 2147483647] = 5):
        await self.db.update_config(interaction.guild_id, channel_announcement.id, voice_xp, chat_xp)
        await interaction.response.send_message(
            f"Pengaturan cepat disimpan: {chat_xp} XP per pesan, {voice_xp} XP per menit voice, "
            f"pengumuman di {channel_announcement.mention}. Pengaturan ini tidak mengubah mode notifikasi atau batas peserta voice."
        )

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
        await interaction.response.send_message(f"Mode pengumuman diubah ke **{mode.name}**.\n*{descriptions[mode.value]}*")

    @app_commands.command(name="status", description="Lihat status kesehatan dan konfigurasi sistem XP.")
    @app_commands.checks.has_permissions(administrator=True)
    async def show_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        bot_member = guild.me

        try:
            config = await self.db.get_guild_config(guild.id)
            filters = await self.db.get_filters(guild.id)
            rewards = await self.db.fetch_all(
                "SELECT level_required, role_id FROM rewards WHERE guild_id = ?",
                (guild.id,)
            )
        except Exception as e:
            self.bot.logger.error("XP_STATUS_DB_FAIL", "Tidak dapat membaca kesehatan konfigurasi XP", error_obj=e, guild_id=guild.id)
            embed = discord.Embed(title="Status XP tidak tersedia", description="Data konfigurasi tidak dapat dibaca. Coba lagi; jika masalah berulang, hubungi pemilik bot.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

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
        chat_active = chat_xp > 0
        voice_configured = voice_xp > 0
        leveling = self.bot.get_cog("Leveling")
        loop_running = bool(leveling and leveling.voice_heartbeat.is_running())
        heartbeat = self.bot.voice_health.get("last_heartbeat_at")
        heartbeat_text = heartbeat or "Belum ada heartbeat"
        heartbeat_age = None
        if heartbeat:
            from datetime import datetime, timezone
            heartbeat_dt = datetime.fromisoformat(heartbeat)
            heartbeat_age = (datetime.now(timezone.utc) - heartbeat_dt).total_seconds()
            heartbeat_text = f"{int(heartbeat_age)} detik lalu"
        voice_ok = loop_running and heartbeat_age is not None and heartbeat_age <= 180 and self.bot.voice_health.get("guild_error", 0) == 0
        mode = config['announcement_mode'].capitalize()
        chat_status = "Aktif" if chat_active else "Nonaktif (rate 0 XP)"
        if not voice_configured:
            voice_status = "Nonaktif (rate 0 XP)"
        elif voice_ok:
            voice_status = "Aktif dan sehat"
        else:
            voice_status = "Aktif, tetapi runtime perlu diperiksa"
        overall_color = discord.Color.green() if (chat_active or voice_ok) else discord.Color.red()

        embed = discord.Embed(
            title="Status XP Jiromi",
            color=overall_color
        )

        embed.add_field(name="Status chat", value=f"{chat_status}\n`{chat_xp} XP` per pesan", inline=True)
        embed.add_field(name="Status voice", value=f"{voice_status}\n`{voice_xp} XP` per menit", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(name="Pengumuman", value=f"Mode: **{mode}**\nChannel: <#{config['announce_channel_id']}>" if config['announce_channel_id'] else f"Mode: **{mode}**\nChannel: belum dipilih", inline=True)
        embed.add_field(name="Batas voice", value=f"Minimal `{config['min_members_voice']} orang`", inline=True)
        embed.add_field(name="Runtime", value=f"Database: sehat\nLeveling cog: {'ada' if leveling else 'hilang'}\nVoice loop: {'aktif' if loop_running else 'mati'}\nHeartbeat: `{heartbeat_text}`\nCommitted: {self.bot.voice_health.get('committed_voice_events', 0)}", inline=False)
        skip_counts = self.bot.voice_health
        embed.add_field(name="Voice tidak diberi XP sejak ringkasan log terakhir (10 menit)", value=(f"Min member {skip_counts['below_min_members']} | bot/self-deaf {skip_counts['self_deaf_or_bot']}\n"
            f"Channel {skip_counts['channel_filter']} | role {skip_counts['role_filter']} | muted {skip_counts['muted_limit']} | member error {skip_counts['member_error']} | guild error {skip_counts['guild_error']}"), inline=False)

        embed.add_field(name="Role whitelist", value=role_allow_str, inline=True)
        embed.add_field(name="Role blacklist", value=role_deny_str, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False) # Spacer

        embed.add_field(name="Channel whitelist", value=chan_allow_str, inline=True)
        embed.add_field(name="Channel blacklist", value=chan_deny_str, inline=True)
        
        reward_stats = (
            f"Total Config: **{len(rewards)}**\n"
            f"Aman: {safe} | Perlu diperiksa: {warning} | Role hilang: {missing}"
        )
        embed.add_field(name="Kondisi reward", value=reward_stats, inline=False)

        if voice_configured and not voice_ok:
            embed.set_footer(text="Langkah berikutnya: periksa runtime voice dan log bot. XP chat tetap berjalan bila rate chat lebih dari 0.")
        elif not chat_active and not voice_configured:
            embed.set_footer(text="Langkah berikutnya: aktifkan rate chat atau voice dengan /xp setup atau /setup.")
        elif warning > 0 or missing > 0:
            embed.set_footer(text="Langkah berikutnya: perbaiki reward role lewat /xp reward list.")
        else:
            embed.set_footer(text="Sistem siap digunakan. Gunakan /xp reward add untuk menambahkan hadiah level.")

        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "Akses ditolak. Perintah konfigurasi XP hanya untuk administrator."
        else:
            self.bot.logger.error("XP_CONFIG_COMMAND_FAIL", "Perintah konfigurasi XP gagal", error_obj=error, guild_id=interaction.guild_id)
            msg = "Pengaturan belum dapat diproses. Coba lagi, lalu periksa log bot bila masalah berulang."
        await send_interaction_error(interaction, msg)

    
    @app_commands.command(name="reset", description="Reset XP semua member di server ini ke 0.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_xp_all(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="Konfirmasi reset XP server",
            description=(
                f"Kamu akan mereset **XP & LEVEL** di server **{interaction.guild.name}**. Total menit voice dan riwayat mingguan tetap tersimpan.\n\n"
                "**Yang akan terjadi:**\n"
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
    
    @app_commands.command(name="reset_user", description="Minta konfirmasi sebelum mereset XP dan level satu member.")
    @app_commands.describe(member="Member yang akan di-reset XP-nya")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_user_xp_cmd(self, interaction: discord.Interaction, member: discord.Member):
        if member.bot:
            await interaction.response.send_message("Bot tidak memiliki XP untuk direset.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Konfirmasi reset member",
            description=(
                f"Member: {member.mention}\n\n"
                "Yang direset: XP dan level menjadi 0.\n"
                "Tetap tersimpan: total menit voice dan riwayat mingguan.\n"
                "Role reward tetap ada; perintah ini tidak mencabut role."
            ),
            color=discord.Color.red(),
        )
        view = ResetUserConfirmView(self.db, interaction.guild_id, interaction.user.id, member)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
            
    @role_group.command(name="remove", description="Hapus role dari Whitelist/Blacklist (Jadikan Netral).")
    @app_commands.checks.has_permissions(administrator=True)
    async def role_remove(self, interaction: discord.Interaction, role: discord.Role):

        await self.db.remove_filter(interaction.guild_id, role.id)
        
        await interaction.response.send_message(
            f"Aturan untuk role {role.mention} telah dihapus. Sekarang role ini **Netral**."
        )
        
    filter_group = app_commands.Group(name="filter", description="Manajemen Filter Global")

    @filter_group.command(name="reset", description="Hapus semua aturan whitelist dan blacklist.")
    @app_commands.checks.has_permissions(administrator=True)
    async def filter_reset_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Konfirmasi reset filter",
            description="Ini akan menghapus semua konfigurasi **Role & Channel** (Whitelist/Blacklist).\nSemua akan kembali ke default.",
            color=discord.Color.red()
        )
        
        view = FilterResetView(self.db, interaction.guild_id, interaction.user.id)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
        
    channel_group = app_commands.Group(name="channel", description="Atur whitelist/blacklist channel untuk XP.")

    @channel_group.command(name="allow", description="Whitelist: hanya channel ini yang bisa mendapat XP.")
    @app_commands.describe(channel="Channel yang ingin diizinkan (Text/Voice)")
    @app_commands.checks.has_permissions(administrator=True)
    async def channel_allow(self, interaction, channel: discord.abc.GuildChannel):

        await self.db.remove_filter(interaction.guild_id, channel.id) 
        
        await self.db.add_filter(interaction.guild_id, channel.id, 'channel', 'allow')
        
        await interaction.response.send_message(
            f"**Whitelist:** XP sekarang aktif di {channel.mention}.\n"
            f"*(Catatan: Jika ini whitelist pertama, channel lain otomatis mati)*"
        )

    @channel_group.command(name="disallow", description="Blacklist: matikan XP di channel ini.")
    @app_commands.describe(channel="Channel yang ingin dimatikan XP-nya")
    @app_commands.checks.has_permissions(administrator=True)
    async def channel_disallow(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):

        await self.db.remove_filter(interaction.guild_id, channel.id)
        
        await self.db.add_filter(interaction.guild_id, channel.id, 'channel', 'exclude')
        
        await interaction.response.send_message(f"**Blacklist:** XP telah dimatikan di {channel.mention}.")

    @channel_group.command(name="remove", description="Hapus filter channel dan kembalikan ke status netral.")
    @app_commands.describe(channel="Channel yang akan dihapus aturannya")
    @app_commands.checks.has_permissions(administrator=True)
    async def channel_remove(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):

        await self.db.remove_filter(interaction.guild_id, channel.id)
        
        await interaction.response.send_message(
            f"Aturan XP di {channel.mention} telah dihapus (status: **Netral**)."
        )

    @app_commands.command(name="refresh_cache", description="Muat ulang cache konfigurasi dan reward.")
    @app_commands.checks.has_permissions(administrator=True)
    async def refresh_cache(self, interaction: discord.Interaction):

        self.db._config_cache.clear()
        self.db._filter_cache.clear()

        self.failed_roles_cache.clear()
        self.reward_roles_cache.clear()

        self.bot.logger.audit("CACHE_FLUSH", f"Admin {interaction.user.name} melakukan refresh cache manual.")

        await interaction.response.send_message(
            "**Cache berhasil diperbarui.**\n"
            "Semua cache (Config, Filter, Role Error) telah dibersihkan.\n"
            "Bot akan mengambil data segar dari Database pada aktivitas berikutnya.",
            ephemeral=True
        )

    # --- BADGE MAINTENANCE ---
    @app_commands.command(name="grant_tenure", description="Berikan badge 'Still Here' untuk member yang bergabung lebih dari 1 tahun.")
    @app_commands.checks.has_permissions(administrator=True)
    async def grant_tenure(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        
        # Ambil semua member (Butuh Intent Members!)
        members = interaction.guild.members
        granted_count = 0
        now = discord.utils.utcnow()
        
        for member in members:
            if member.bot: continue
            
            # Cek Join Date
            if not member.joined_at: continue
            
            # Hitung selisih hari
            delta = now - member.joined_at
            
            if delta.days >= 365:
                # Coba unlock (Fail silent kalau sudah punya)
                if await self.db.unlock_badge(member.id, interaction.guild_id, "badge_still_here"):
                    granted_count += 1
        
        await interaction.followup.send(
            f"**Pemeriksaan masa keanggotaan selesai.**\n"
            f"Badge **Still Here** diberikan kepada **{granted_count}** veteran yang telah bergabung > 1 tahun."
        )

async def setup(bot):
    """Fungsi inisialisasi global untuk discord.py agar bisa memuat Cog ini."""
    await bot.add_cog(AdminConfig(bot, bot.db))
