import re
import string
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from utils.interaction_responses import send_interaction_error, send_interaction_message
from utils.views import ExecutorView


EVENT_TYPES = [
    app_commands.Choice(name="Welcome (member masuk)", value="welcome"),
    app_commands.Choice(name="Leave (member keluar)", value="leave"),
    app_commands.Choice(name="Ban", value="ban"),
    app_commands.Choice(name="Boost Nitro", value="boost"),
]
PLACEHOLDERS = {"member", "username", "server", "member_count", "count", "boost_count"}
PLACEHOLDER_MAX_LENGTHS = {
    "member": 22,
    "username": 32,
    "server": 100,
    "member_count": 20,
    "count": 20,
    "boost_count": 20,
}
MAX_MESSAGE_LENGTH = 2000
MAX_TITLE_LENGTH = 256
MAX_DESCRIPTION_LENGTH = 4096
MAX_IMAGE_URL_LENGTH = 2000


class EventTestView(ExecutorView):
    def __init__(self, author_id, channel, content, embed):
        super().__init__(author_id)
        self.channel = channel
        self.content = content
        self.embed = embed
        self._finished = False

    @discord.ui.button(label="Kirim simulasi", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self._finished:
            await send_interaction_error(interaction, "Simulasi sedang diproses atau sudah selesai.")
            return
        self._finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Simulasi sedang dikirim...", view=self)
        try:
            await self.channel.send(content=self.content or None, embed=self.embed)
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="Bot tidak dapat mengirim simulasi. Periksa izin Kirim Pesan dan Embed Links pada channel tujuan.", view=None
            )
        except discord.HTTPException as error:
            logger = getattr(interaction.client, "logger", None)
            if logger:
                logger.error("EVENT_TEST_SEND_FAIL", "Pengiriman simulasi event gagal", error_obj=error, guild_id=interaction.guild_id)
            await interaction.edit_original_response(
                content="Simulasi tidak terkirim. Coba lagi setelah memeriksa konfigurasi event.", view=None
            )
        else:
            await interaction.edit_original_response(content=f"Simulasi terkirim ke {self.channel.mention}.", view=None)
        self.stop()

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self._finished:
            await send_interaction_error(interaction, "Simulasi sedang diproses atau sudah selesai.")
            return
        self._finished = True
        await interaction.response.edit_message(content="Pengiriman simulasi dibatalkan.", view=None)
        self.stop()


class EventResetView(ExecutorView):
    def __init__(self, author_id, cog, guild_id, event_type, event_name):
        super().__init__(author_id)
        self.cog = cog
        self.guild_id = guild_id
        self.event_type = event_type
        self.event_name = event_name

    @discord.ui.button(label="Reset event", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.cog.db.clear_event_config(self.guild_id, self.event_type)
        await interaction.response.edit_message(
            content=f"Konfigurasi {self.event_name} direset. Channel dan status aktif juga dihapus.", view=None
        )
        self.stop()

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(content="Reset event dibatalkan.", view=None)
        self.stop()


class ServerEvents(commands.Cog):
    DEFAULT_MESSAGES = {
        "welcome": "Selamat datang {member} di **{server}**!",
        "leave": "{username} telah meninggalkan **{server}**.",
        "ban": "{username} telah dikeluarkan dari **{server}**.",
        "boost": "Terima kasih {member} telah boost **{server}**!",
    }
    event_group = app_commands.Group(name="event", description="Atur pesan Welcome, Leave, Ban, dan Boost.")

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    @staticmethod
    def _validate_placeholders(value, label):
        if value is None:
            return None
        try:
            fields = string.Formatter().parse(value)
            for _literal, field, format_spec, conversion in fields:
                if field is not None and (field not in PLACEHOLDERS or format_spec or conversion):
                    return f"Placeholder `{{{field}}}` pada {label} tidak tersedia. Gunakan /help topik:placeholders."
        except ValueError:
            return f"{label} memiliki kurung kurawal yang belum lengkap."
        return None

    def _validate_text(self, value, label, maximum):
        if value is not None and len(value) > maximum:
            return f"{label} maksimal {maximum} karakter."
        error = self._validate_placeholders(value, label)
        if error or value is None:
            return error
        upper_bound = len(value)
        for _literal, field, _format_spec, _conversion in string.Formatter().parse(value):
            if field is not None:
                upper_bound += PLACEHOLDER_MAX_LENGTHS[field] - len(field) - 2
        if upper_bound > maximum:
            return (
                f"{label} dapat melebihi {maximum} karakter setelah placeholder diganti. "
                "Pendekkan teks di sekitarnya atau hapus placeholder."
            )
        return None

    @staticmethod
    def _parse_color(color_hex):
        if color_hex is None:
            return None, None
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", color_hex):
            return None, "Warna harus berupa kode hex enam digit, misalnya `#5865F2`."
        return int(color_hex.removeprefix("#"), 16), None

    @staticmethod
    def _validate_image_url(url):
        if len(url) > MAX_IMAGE_URL_LENGTH:
            return f"URL gambar maksimal {MAX_IMAGE_URL_LENGTH} karakter."
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "URL gambar harus memakai `https://` atau `http://` dan memiliki alamat host."
        return None

    def _format_text(self, text, member, guild):
        if not text:
            return ""
        return text.format(
            member=member.mention, username=member.name, server=guild.name,
            member_count=guild.member_count, count=guild.member_count,
            boost_count=guild.premium_subscription_count,
        )

    @staticmethod
    def _message_chunks(value, maximum=1900):
        return [value[index:index + maximum] for index in range(0, len(value), maximum)] or ["Kosong"]

    def _build_event_payload(self, event_type, config, member, guild):
        message_template = config["message_text"]
        if message_template is None:
            message_template = self.DEFAULT_MESSAGES[event_type]
        content = self._format_text(message_template, member, guild)
        if len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError("Pesan teks event melebihi 2.000 karakter setelah placeholder diganti.")
        embed = None
        if config["use_embed"]:
            title = self._format_text(config["embed_title"], member, guild)
            description = self._format_text(config["embed_description"], member, guild)
            if len(title) > MAX_TITLE_LENGTH:
                raise ValueError("Judul embed event melebihi 256 karakter setelah placeholder diganti.")
            if len(description) > MAX_DESCRIPTION_LENGTH:
                raise ValueError("Deskripsi embed event melebihi 4.096 karakter setelah placeholder diganti.")
            embed = discord.Embed(
                title=title or None,
                description=description or None,
                color=discord.Color(config["embed_color"] or discord.Color.blue().value),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            if config["image_url"]:
                embed.set_image(url=config["image_url"])
        if not content and embed is None:
            raise ValueError("Event tidak memiliki isi. Atur pesan teks atau aktifkan embed sebelum mengirim.")
        return content, embed

    def _get_channel_issue(self, guild, config):
        if not config["channel_id"]:
            return None, "Channel tujuan belum dipilih. Jalankan /event setup."
        channel = guild.get_channel(config["channel_id"])
        if channel is None:
            return None, "Channel tujuan tidak ditemukan. Pilih channel baru dengan /event setup."
        me = guild.me or guild.get_member(self.bot.user.id)
        permissions = channel.permissions_for(me)
        if not permissions.send_messages:
            return None, "Bot tidak memiliki izin Kirim Pesan pada channel tujuan."
        if config["use_embed"] and not permissions.embed_links:
            return None, "Bot tidak memiliki izin Embed Links pada channel tujuan."
        return channel, None

    async def _send_event(self, event_type, member, guild):
        config = await self.db.get_event_config(guild.id, event_type)
        if not config or not config["is_enabled"]:
            return False, "Event tidak aktif atau belum dikonfigurasi."
        channel, issue = self._get_channel_issue(guild, config)
        if issue:
            return False, issue
        try:
            content, embed = self._build_event_payload(event_type, config, member, guild)
        except ValueError as exc:
            logger = getattr(self.bot, "logger", None)
            if logger:
                logger.error("EVENT_PAYLOAD_INVALID", "Konfigurasi event melebihi batas Discord", error_obj=exc, event_type=event_type)
            return False, str(exc)
        try:
            await channel.send(content=content or None, embed=embed)
            return True, None
        except discord.Forbidden:
            return False, "Bot tidak diizinkan mengirim pesan pada channel tujuan."
        except discord.HTTPException as exc:
            logger = getattr(self.bot, "logger", None)
            if logger:
                logger.error("EVENT_SEND_FAIL", "Pengiriman event gagal", error_obj=exc, event_type=event_type)
            return False, "Discord menolak pengiriman event."

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self._send_event("welcome", member, member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self._send_event("leave", member, member.guild)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        class BannedUser:
            name = user.name
            mention = user.mention
            display_avatar = user.display_avatar
        await self._send_event("ban", BannedUser(), guild)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.premium_since is None and after.premium_since is not None:
            await self._send_event("boost", after, after.guild)

    @event_group.command(name="setup", description="Pilih channel tujuan dan aktifkan event.")
    @app_commands.describe(event_type="Tipe event", channel="Channel tujuan notifikasi")
    @app_commands.choices(event_type=EVENT_TYPES)
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_event(self, interaction, event_type: app_commands.Choice[str], channel: discord.TextChannel):
        await self.db.update_event_config(interaction.guild_id, event_type.value, {"channel_id": channel.id, "is_enabled": 1})
        await send_interaction_message(interaction, content=f"{event_type.name} aktif dan akan dikirim ke {channel.mention}. Atur isi dengan /event message atau /event embed.")

    @event_group.command(name="toggle", description="Nyalakan atau matikan event tanpa menghapus konfigurasi.")
    @app_commands.choices(event_type=EVENT_TYPES, status=[app_commands.Choice(name="Aktif", value=1), app_commands.Choice(name="Nonaktif", value=0)])
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_event(self, interaction, event_type: app_commands.Choice[str], status: app_commands.Choice[int]):
        await self.db.update_event_config(interaction.guild_id, event_type.value, {"is_enabled": status.value})
        state = "aktif" if status.value else "nonaktif"
        await send_interaction_message(interaction, content=f"Event {event_type.name} sekarang {state}. Konfigurasi lain tetap tersimpan.")

    @event_group.command(name="message", description="Atur pesan teks event dan placeholder yang didukung.")
    @app_commands.describe(event_type="Tipe event", content="Maksimal 2.000 karakter; gunakan /help topik:placeholders")
    @app_commands.choices(event_type=EVENT_TYPES)
    @app_commands.checks.has_permissions(administrator=True)
    async def set_message(self, interaction, event_type: app_commands.Choice[str], content: str):
        error = self._validate_text(content, "Pesan teks", MAX_MESSAGE_LENGTH)
        if error:
            await send_interaction_error(interaction, error)
            return
        await self.db.update_event_config(interaction.guild_id, event_type.value, {"message_text": content})
        await send_interaction_message(interaction, content=f"Pesan teks {event_type.name} disimpan. Gunakan /event preview untuk memeriksa hasilnya.")

    @event_group.command(name="embed", description="Atur embed event dalam satu penyimpanan aman.")
    @app_commands.describe(event_type="Tipe event", use_embed="Gunakan embed", title="Opsional, maksimal 256 karakter", description="Opsional, maksimal 4.096 karakter", color_hex="Opsional, contoh #5865F2")
    @app_commands.choices(event_type=EVENT_TYPES)
    @app_commands.checks.has_permissions(administrator=True)
    async def set_embed(self, interaction, event_type: app_commands.Choice[str], use_embed: bool, title: str = None, description: str = None, color_hex: str = None):
        for value, label, maximum in ((title, "Judul embed", MAX_TITLE_LENGTH), (description, "Deskripsi embed", MAX_DESCRIPTION_LENGTH)):
            error = self._validate_text(value, label, maximum)
            if error:
                await send_interaction_error(interaction, error)
                return
        color, error = self._parse_color(color_hex)
        if error:
            await send_interaction_error(interaction, error)
            return
        values = {"use_embed": int(use_embed)}
        if title is not None:
            values["embed_title"] = title
        if description is not None:
            values["embed_description"] = description
        if color is not None:
            values["embed_color"] = color
        await self.db.update_event_config(interaction.guild_id, event_type.value, values)
        state = "aktif" if use_embed else "nonaktif"
        await send_interaction_message(interaction, content=f"Embed {event_type.name} disimpan dan sekarang {state}. Gunakan /event preview untuk memeriksa hasilnya.")

    @event_group.command(name="image", description="Atur gambar atau GIF publik untuk embed.")
    @app_commands.describe(event_type="Tipe event", url="URL http/https langsung, maksimal 2.000 karakter")
    @app_commands.choices(event_type=EVENT_TYPES)
    @app_commands.checks.has_permissions(administrator=True)
    async def set_image(self, interaction, event_type: app_commands.Choice[str], url: str):
        error = self._validate_image_url(url)
        if error:
            await send_interaction_error(interaction, error)
            return
        await self.db.update_event_config(interaction.guild_id, event_type.value, {"image_url": url})
        await send_interaction_message(interaction, content=f"Gambar untuk {event_type.name} disimpan. Gambar hanya tampil saat embed aktif.")

    @event_group.command(name="clear", description="Hapus bagian konten event atau reset seluruh konfigurasi.")
    @app_commands.choices(event_type=EVENT_TYPES, section=[app_commands.Choice(name="Pesan teks", value="message"), app_commands.Choice(name="Konten embed", value="embed"), app_commands.Choice(name="Gambar", value="image"), app_commands.Choice(name="Reset seluruh event", value="reset")])
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_event(self, interaction, event_type: app_commands.Choice[str], section: app_commands.Choice[str]):
        if section.value == "reset":
            view = EventResetView(interaction.user.id, self, interaction.guild_id, event_type.value, event_type.name)
            await send_interaction_message(interaction, content=f"Reset seluruh konfigurasi {event_type.name}? Channel dan status aktif juga akan dihapus.", view=view)
            view.message = await interaction.original_response()
            return
        values = {"message": {"message_text": ""}, "embed": {"use_embed": 0, "embed_title": None, "embed_description": None, "embed_color": 0}, "image": {"image_url": None}}[section.value]
        await self.db.update_event_config(interaction.guild_id, event_type.value, values)
        await send_interaction_message(interaction, content=f"{section.name} untuk {event_type.name} dihapus. Channel dan status aktif tetap tersimpan.")

    @event_group.command(name="preview", description="Lihat hasil event secara privat sebelum dikirim.")
    @app_commands.choices(event_type=EVENT_TYPES)
    @app_commands.checks.has_permissions(administrator=True)
    async def preview_event(self, interaction, event_type: app_commands.Choice[str]):
        config = await self.db.get_event_config(interaction.guild_id, event_type.value)
        if not config:
            await send_interaction_error(interaction, f"Event {event_type.name} belum dikonfigurasi. Jalankan /event setup terlebih dahulu.")
            return
        try:
            content, embed = self._build_event_payload(event_type.value, config, interaction.user, interaction.guild)
        except ValueError as exc:
            await send_interaction_error(interaction, f"Konfigurasi event perlu diperbaiki: {exc}")
            return
        await send_interaction_message(interaction, content=content or "Preview tidak memiliki pesan teks.", embed=embed)

    @event_group.command(name="test", description="Kirim simulasi ke channel tujuan setelah konfirmasi.")
    @app_commands.choices(event_type=EVENT_TYPES)
    @app_commands.checks.has_permissions(administrator=True)
    async def test_event(self, interaction, event_type: app_commands.Choice[str]):
        config = await self.db.get_event_config(interaction.guild_id, event_type.value)
        if not config:
            await send_interaction_error(interaction, f"Event {event_type.name} belum dikonfigurasi. Jalankan /event setup terlebih dahulu.")
            return
        channel, issue = self._get_channel_issue(interaction.guild, config)
        if issue:
            await send_interaction_error(interaction, issue)
            return
        try:
            content, embed = self._build_event_payload(event_type.value, config, interaction.user, interaction.guild)
        except ValueError as exc:
            await send_interaction_error(interaction, f"Konfigurasi event perlu diperbaiki: {exc}")
            return
        view = EventTestView(interaction.user.id, channel, content, embed)
        state = "aktif" if config["is_enabled"] else "nonaktif"
        await send_interaction_message(interaction, content=f"Simulasi {event_type.name} akan dikirim ke {channel.mention}. Event saat ini {state}. Konfirmasi pengiriman publik.", view=view)
        view.message = await interaction.original_response()

    @event_group.command(name="show", description="Lihat status, isi, dan kesiapan pengiriman event.")
    @app_commands.choices(event_type=EVENT_TYPES)
    @app_commands.checks.has_permissions(administrator=True)
    async def show_event_config(self, interaction, event_type: app_commands.Choice[str]):
        config = await self.db.get_event_config(interaction.guild_id, event_type.value)
        if not config:
            await send_interaction_error(interaction, f"Event {event_type.name} belum dikonfigurasi. Jalankan /event setup terlebih dahulu.")
            return
        channel, issue = self._get_channel_issue(interaction.guild, config)
        embed = discord.Embed(title=f"Konfigurasi event: {event_type.name}", color=discord.Color.teal())
        embed.add_field(name="Status", value="Aktif" if config["is_enabled"] else "Nonaktif", inline=True)
        embed.add_field(name="Channel tujuan", value=channel.mention if channel else "Belum tersedia", inline=True)
        embed.add_field(name="Mode", value="Embed" if config["use_embed"] else "Pesan teks", inline=True)
        if config["message_text"] is None:
            message_state = "Menggunakan pesan bawaan"
        elif config["message_text"] == "":
            message_state = "Dikosongkan"
        else:
            message_state = "Diatur"
        embed.add_field(name="Pesan teks", value=message_state, inline=False)
        if config["use_embed"]:
            embed.add_field(name="Judul embed", value="Diatur" if config["embed_title"] else "Kosong", inline=False)
            embed.add_field(name="Deskripsi embed", value="Diatur" if config["embed_description"] else "Kosong", inline=False)
            embed.add_field(name="Warna", value=f"#{(config['embed_color'] or discord.Color.blue().value):06X}", inline=True)
        if config["image_url"]:
            embed.add_field(name="Gambar", value="Diatur; URL lengkap dan preview dikirim di bawah.", inline=False)
        if issue:
            embed.add_field(name="Perlu diperbaiki", value=issue, inline=False)
        else:
            embed.add_field(name="Kesiapan pengiriman", value="Channel dan izin bot siap. Gunakan /event preview atau /event test.", inline=False)
        await send_interaction_message(interaction, embed=embed)
        raw_details = [
            ("Pesan teks", self.DEFAULT_MESSAGES[event_type.value] if config["message_text"] is None else config["message_text"] or "Kosong (dikosongkan)"),
        ]
        if config["use_embed"]:
            raw_details.extend([
                ("Judul embed", config["embed_title"] or "Kosong"),
                ("Deskripsi embed", config["embed_description"] or "Kosong"),
            ])
        for label, value in raw_details:
            for index, chunk in enumerate(self._message_chunks(value), start=1):
                suffix = f" ({index})" if len(value) > 1900 else ""
                await interaction.followup.send(content=f"{label}{suffix}:\n{chunk}", ephemeral=True)
        if config["image_url"]:
            await interaction.followup.send(content=config["image_url"], ephemeral=True)
        try:
            content, preview = self._build_event_payload(event_type.value, config, interaction.user, interaction.guild)
        except ValueError as exc:
            await interaction.followup.send(content=f"Preview tidak dapat dibuat: {exc}", ephemeral=True)
            return
        await interaction.followup.send(content=content or "Preview tidak memiliki pesan teks.", embed=preview, ephemeral=True)

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await send_interaction_error(interaction, "Akses ditolak. Perintah event memerlukan izin Administrator.")
            return
        logger = getattr(self.bot, "logger", None)
        if logger:
            logger.error("EVENT_COMMAND_FAIL", "Perintah event gagal", error_obj=error)
        await send_interaction_error(interaction, "Perintah event tidak dapat diproses. Coba lagi.")


async def setup(bot):
    await bot.add_cog(ServerEvents(bot, bot.db))
