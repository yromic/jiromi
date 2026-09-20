# cogs/server_events.py
import discord
from discord import app_commands
from discord.ext import commands

class ServerEvents(commands.Cog):
    # [TAMBAHAN BARU] Default messages agar bot tidak error saat config kosong
    DEFAULT_MESSAGES = {
        "welcome": "👋 Selamat datang {member} di **{server}**!",
        "leave": "👋 {username} telah meninggalkan **{server}**.",
        "ban": "🔨 {username} telah dibanned dari **{server}**.",
        "boost": "🚀 Terima kasih {member} telah boost **{server}**!"
    }

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        #self.bot.tree.add_command(self.event_group)

    
    def _format_text(self, text, member, guild):
        """Mengganti placeholder dengan aman."""
        if not text: 
            return ""
        
        # Mapping data
        data = {
            "member": member.mention,
            "username": member.name,
            "server": guild.name,
            "member_count": guild.member_count,
            "count": guild.member_count,
            "boost_count": guild.premium_subscription_count
        }

        # [FIX] Try-except agar tidak crash jika admin typo placeholder
        try:
            return text.format(**data)
        except KeyError:
            return text

    async def _send_event(self, event_type, member, guild):
        """Logic inti pengiriman pesan event."""
        config = await self.db.get_event_config(guild.id, event_type)
        
        # 1. Guard Clauses (Cek Database)
        if not config: return
        if not config['is_enabled']: return
        if not config['channel_id']: return

        # 2. Guard Clause (Cek Channel)
        channel = guild.get_channel(config['channel_id'])
        if not channel: return
        
        # Cek permission dasar bot di channel tersebut
        me = guild.me or guild.get_member(self.bot.user.id)
        permissions = channel.permissions_for(me)
        
        if not permissions.send_messages: return

        # 3. Siapkan konten pesan (Gunakan Default jika kosong)
        raw_text = config['message_text']
        if not raw_text:
            raw_text = self.DEFAULT_MESSAGES.get(event_type, "")

        content_msg = self._format_text(raw_text, member, guild)
        embed_obj = None

        # 4. Build Embed (Jika diaktifkan)
        if config['use_embed']:
            title = self._format_text(config['embed_title'], member, guild)
            desc = self._format_text(config['embed_description'], member, guild)
            
            # Konversi int ke discord.Color secara eksplisit
            color_val = config['embed_color']
            color = discord.Color(color_val) if color_val else discord.Color.blue()
            
            embed_obj = discord.Embed(
                title=title or None,
                description=desc or None,
                color=color
            )
            
            # Auto Thumbnail: Avatar Member
            embed_obj.set_thumbnail(url=member.display_avatar.url)
            
            # Static Image (jika ada URL valid)
            if config['image_url'] and config['image_url'].startswith("http"):
                embed_obj.set_image(url=config['image_url'])

        # [FIX] Guard Clause Terakhir: Jika pesan & embed kosong, batalkan.
        if not content_msg and not embed_obj:
            return

        # 5. Kirim Pesan (Safety Try-Except)
        try:
            await channel.send(content=content_msg or None, embed=embed_obj)
        except discord.Forbidden:
            print(f"❌ Izin ditolak saat mengirim {event_type} di {guild.name}")
        except Exception as e:
            print(f"❌ Error event {event_type}: {e}")

    # --- LISTENERS ---

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self._send_event('welcome', member, member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Trigger saat user leave atau di-kick
        await self._send_event('leave', member, member.guild)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        # Mock member object karena user banned bukan lagi Member
        class MockMember:
            def __init__(self, u, g):
                self.name = u.name
                self.mention = u.mention
                self.id = u.id
                self.guild = g
                self.display_avatar = u.display_avatar
        
        mock_mem = MockMember(user, guild)
        await self._send_event('ban', mock_mem, guild)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Deteksi Nitro Boost
        if before.premium_since is None and after.premium_since is not None:
            await self._send_event('boost', after, after.guild)

    # --- SLASH COMMANDS (Admin Config) ---

    event_group = app_commands.Group(name="event", description="Konfigurasi pesan Welcome, Leave, Ban, & Boost.")

    @event_group.command(name="setup", description="Aktifkan event dan set channel tujuan.")
    @app_commands.describe(event_type="Pilih tipe event", channel="Channel tujuan notifikasi")
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Welcome (Member Masuk)", value="welcome"),
        app_commands.Choice(name="Leave (Member Keluar)", value="leave"),
        app_commands.Choice(name="Ban (Member Dibanned)", value="ban"),
        app_commands.Choice(name="Boost (Nitro Boost)", value="boost"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_event(self, interaction: discord.Interaction, event_type: app_commands.Choice[str], channel: discord.TextChannel):
        await self.db.set_event_config(interaction.guild_id, event_type.value, "channel_id", channel.id)
        await self.db.set_event_config(interaction.guild_id, event_type.value, "is_enabled", 1)
        
        await interaction.response.send_message(
            f"✅ **{event_type.name}** diaktifkan! Pesan akan dikirim ke {channel.mention}.\n"
            f"Gunakan `/event message` atau `/event embed` untuk mengatur isi pesan."
        )

    @event_group.command(name="toggle", description="Nyalakan atau matikan event tanpa menghapus config.")
    @app_commands.choices(status=[
        app_commands.Choice(name="ON (Aktif)", value=1),
        app_commands.Choice(name="OFF (Mati)", value=0)
    ], event_type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Leave", value="leave"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Boost", value="boost"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_event(self, interaction: discord.Interaction, event_type: app_commands.Choice[str], status: app_commands.Choice[int]):
        await self.db.set_event_config(interaction.guild_id, event_type.value, "is_enabled", status.value)
        state = "Aktif" if status.value == 1 else "Non-Aktif"
        await interaction.response.send_message(f"⚙️ Event **{event_type.name}** sekarang **{state}**.")

    @event_group.command(name="message", description="Atur pesan teks biasa (non-embed). Gunakan {member}, {server}, dll.")
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Leave", value="leave"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Boost", value="boost"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_message(self, interaction: discord.Interaction, event_type: app_commands.Choice[str], content: str):
        # Jika content kosong, kita anggap menghapus pesan teks
        await self.db.set_event_config(interaction.guild_id, event_type.value, "message_text", content)
        await interaction.response.send_message(f"📝 Pesan teks untuk **{event_type.name}** telah diperbarui.")

    @event_group.command(name="embed", description="Atur tampilan embed.")
    @app_commands.describe(
        use_embed="Gunakan embed?", 
        title="Judul Embed (Bisa pakai {username})", 
        description="Isi Embed (Bisa pakai {member}, {count})",
        color_hex="Kode warna Hex (contoh: #ff0000)"
    )
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Leave", value="leave"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Boost", value="boost"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_embed(self, interaction: discord.Interaction, 
                        event_type: app_commands.Choice[str], 
                        use_embed: bool, 
                        title: str = None, 
                        description: str = None, 
                        color_hex: str = None):
        
        # Update switch embed
        await self.db.set_event_config(interaction.guild_id, event_type.value, "use_embed", 1 if use_embed else 0)
        
        if title:
            await self.db.set_event_config(interaction.guild_id, event_type.value, "embed_title", title)
        if description:
            await self.db.set_event_config(interaction.guild_id, event_type.value, "embed_description", description)
        if color_hex:
            # Konversi Hex String (#ff0000) ke Integer
            try:
                color_clean = color_hex.strip("#")
                color_int = int(color_clean, 16)
                await self.db.set_event_config(interaction.guild_id, event_type.value, "embed_color", color_int)
            except ValueError:
                return await interaction.response.send_message("❌ Format warna salah. Gunakan hex code, misal: `#ff0000`", ephemeral=True)

        await interaction.response.send_message(f"🖼️ Pengaturan Embed **{event_type.name}** diperbarui!")

    @event_group.command(name="image", description="Set gambar statis/GIF untuk embed via URL.")
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Leave", value="leave"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Boost", value="boost"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_image(self, interaction: discord.Interaction, event_type: app_commands.Choice[str], url: str):
        await self.db.set_event_config(interaction.guild_id, event_type.value, "image_url", url)
        await interaction.response.send_message(f"📷 Gambar background untuk **{event_type.name}** telah diset.")

    @event_group.command(name="test", description="Kirim simulasi pesan event ke channel tujuan.")
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Leave", value="leave"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Boost", value="boost"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def test_event(self, interaction: discord.Interaction, event_type: app_commands.Choice[str]):
        # Defer response agar tidak timeout saat processing
        await interaction.response.defer(ephemeral=True)
        
        # Kirim event palsu
        await self._send_event(event_type.value, interaction.user, interaction.guild)
        
        await interaction.followup.send(f"✅ Simulasi **{event_type.name}** dikirim! Cek channel tujuan.")

    @event_group.command(name="show", description="Lihat konfigurasi event yang sedang tersimpan saat ini.")
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Welcome", value="welcome"),
        app_commands.Choice(name="Leave", value="leave"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Boost", value="boost"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def show_event_config(self, interaction: discord.Interaction, event_type: app_commands.Choice[str]):
        # 1. Ambil data config dari database
        config = await self.db.get_event_config(interaction.guild_id, event_type.value)

        # 2. Jika config belum pernah dibuat sama sekali
        if not config:
            embed = discord.Embed(
                description=f" ❌  Event **{event_type.name}** belum pernah di-setup.",
                color=discord.Color.light_gray()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 3. Parsing data untuk tampilan (Status Icon & Text)
        status = "✅  **AKTIF**" if config['is_enabled'] else "❌  **NON-AKTIF**"
        
        # Cek Channel (Handle jika channel sudah dihapus)
        channel_id = config['channel_id']
        channel = interaction.guild.get_channel(channel_id)
        channel_text = channel.mention if channel else f"⚠️ *Channel Hilang ({channel_id})*"

        # Cek komponen pesan
        use_embed = "✅ Ya" if config['use_embed'] else "❌ Tidak"
        has_msg = "✅ Ada" if config['message_text'] else "❌ Kosong"
        has_img = "✅ Ada" if config['image_url'] else "❌ Tidak ada"

        # 4. Buat Embed Snapshot
        embed = discord.Embed(
            title=f" ⚙️  Config: {event_type.name}",
            color=discord.Color.teal()
        )
        
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Channel Tujuan", value=channel_text, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) # Spacer agar rapi 2 kolom

        embed.add_field(name="Pakai Embed?", value=use_embed, inline=True)
        embed.add_field(name="Pesan Teks?", value=has_msg, inline=True)
        embed.add_field(name="Gambar/GIF?", value=has_img, inline=True)

        # (Opsional) Tampilkan preview isi pesan sedikit
        if config['message_text']:
            preview = (config['message_text'][:50] + '...') if len(config['message_text']) > 50 else config['message_text']
            embed.add_field(name="Preview Pesan Teks", value=f"_{preview}_", inline=False)

        embed.set_footer(text=f"Gunakan /event test {event_type.value} untuk melihat hasil jadinya.")

        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            message = "⛔ **Akses Ditolak:** Kamu tidak memiliki izin Administrator untuk menggunakan perintah ini."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        else:
            print(f"❌ Error pada command event: {error}")

async def setup(bot):
    await bot.add_cog(ServerEvents(bot, bot.db))
