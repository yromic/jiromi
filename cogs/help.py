import discord
from discord import app_commands
from discord.ext import commands


class HelpSystem(commands.Cog):
    def __init__(self, bot, db=None):
        self.bot = bot
        self.db = db

    def _get_embed(self, topic: str) -> discord.Embed:
        """Return the concise command guide for the selected help topic."""
        embed = discord.Embed(color=discord.Color.blue())
        pages = {
            "main": ("Panduan Jiromi", "Pilih topik sesuai peranmu.\n\n**Member**\n`/help topik:user` — aturan XP\n`/help topik:profile` — profil, rank, level, title, dan leaderboard\n\n**Administrator server**\n`/help topik:setup` — mulai konfigurasi\n`/help topik:xp` — konfigurasi XP, filter, reward, dan reset\n`/help topik:event` — pesan Welcome, Leave, Ban, dan Boost\n`/help topik:weekly` — rekap mingguan\n\n**Owner bot**\n`/help topik:owner` — alat pemulihan, backup, dan daftar guild"),
            "user": ("Aturan XP", "**Chat**\nPesan mendapat XP jika berisi minimal 8 karakter dan pengirim belum mendapat XP chat dalam 10 detik terakhir. Role dan channel juga harus lolos filter server.\n\n**Voice**\nPengecekan berjalan tiap menit. Channel harus memiliki setidaknya jumlah peserta manusia aktif yang diatur admin; bot dan anggota yang self-deaf tidak dihitung. Self-deaf tidak mendapat XP. Self-mute atau server mute masih mendapat XP pada lima menit pertama berturut-turut, lalu XP berhenti sampai mute dilepas. Filter role dan channel juga berlaku.\n\nLihat `/xp status` bersama admin untuk memeriksa konfigurasi dan kesehatan voice. Status itu membantu diagnosis, tetapi bukan bukti bahwa setiap sumber XP pasti berjalan untuk setiap anggota."),
            "profile": ("Perintah Member", "`/profile [member]` — tampilan perjalanan, badge, kehadiran, dan pencapaian.\n`/rank [member]` — posisi rank anggota di server.\n`/level [member]` — progres level anggota.\n`/leaderboard` — Top 50 anggota berdasarkan XP; menit voice ditampilkan sebagai konteks.\n`/weekly_leaderboard` — ringkasan aktivitas server pada minggu berjalan.\n`/global leaderboard` — Top 10 server aktif minggu ini; server lain dianonimkan.\n`/title list` — daftar title yang telah dibuka.\n`/title select` — pilih atau lepas title melalui menu."),
            "setup": ("Mulai Konfigurasi", "Semua perintah di halaman ini memerlukan izin Administrator.\n\n`/setup` adalah wizard interaktif untuk memilih preset, channel pengumuman, mode notifikasi, dan batas peserta voice. Ini jalur yang disarankan untuk konfigurasi awal.\n\n`/xp setup channel_announcement:#channel voice_xp:10 chat_xp:5` adalah konfigurasi langsung. `channel_announcement` wajib; `voice_xp` dan `chat_xp` opsional dengan nilai bawaan 10 dan 5.\n\nGunakan `/xp announcement mode:quiet|balanced|loud` untuk notifikasi kenaikan level, lalu `/xp status` untuk melihat konfigurasi, filter, reward, dan kesehatan runtime."),
            "xp": ("Kontrol XP Administrator", "**Filter**\n`/xp role allow role:@Role`, `/xp role disallow role:@Role`, `/xp role remove role:@Role`\n`/xp channel allow channel:#channel`, `/xp channel disallow channel:#channel`, `/xp channel remove channel:#channel`\nWhitelist channel membatasi XP ke channel yang diizinkan; blacklist menolak channel tertentu. Whitelist role membatasi XP ke role tersebut; blacklist role menolak role tersebut. `/xp filter reset` menghapus seluruh filter role dan channel setelah konfirmasi.\n\n**Reward dan pemeliharaan**\n`/xp reward add level:5 role:@Role` dan `/xp reward list` mengelola reward. Role bot harus berada di atas role reward.\n`/xp refresh_cache` memuat ulang cache konfigurasi dan reward. `/xp grant_tenure` memberi badge Still Here kepada anggota yang telah bergabung setidaknya 365 hari.\n\n**Reset**\n`/xp reset` mengatur XP dan level seluruh anggota ke 0 setelah konfirmasi. `/xp reset_user member:@Member` melakukan hal yang sama untuk satu anggota. Keduanya mempertahankan total menit voice dan riwayat mingguan; role reward yang sudah dimiliki tidak dicabut otomatis."),
            "event": ("Event Administrator", "Semua perintah event memerlukan izin Administrator. Tipe `event_type` yang tersedia: `welcome`, `leave`, `ban`, dan `boost`.\n\n**Konfigurasi**\n`/event setup event_type:welcome channel:#channel` menyimpan channel dan langsung mengaktifkan event.\n`/event toggle event_type:welcome status:on|off` menyalakan atau mematikan tanpa menghapus konfigurasi.\n`/event message event_type:welcome content:...` mengatur pesan teks.\n`/event embed event_type:welcome use_embed:true title:... description:... color_hex:#5865F2` mengatur embed; title, description, dan color_hex opsional.\n`/event image event_type:welcome url:https://...` menyimpan gambar atau GIF untuk embed. Gunakan URL publik langsung ke berkas gambar, seperti `.png`, `.jpg`, atau `.gif`; tautan halaman galeri sering tidak dapat dimuat Discord.\n\n**Periksa dan pulihkan**\n`/event show event_type:welcome` menampilkan status dan konfigurasi, lalu `/event test event_type:welcome` mengirim simulasi. Tidak ada `/event clear` yang terdaftar; gunakan toggle untuk menghentikan pengiriman. Jika event tidak terkirim, cek status aktif, channel tujuan, dan izin bot untuk melihat serta mengirim pesan; jalankan `/event setup` lagi bila channel hilang atau salah."),
            "placeholders": ("Placeholder Event", "Gunakan placeholder berikut pada pesan teks atau bagian embed:\n`{member}` — mention anggota\n`{username}` — nama anggota\n`{server}` — nama server\n`{member_count}` — jumlah anggota server\n`{count}` — alias jumlah anggota server\n`{boost_count}` — jumlah Nitro Boost\n\nContoh: `Halo {member}, selamat datang di {server}! Kamu anggota ke-{member_count}.`\nGunakan huruf kecil dan jangan beri spasi di dalam kurung kurawal."),
            "weekly": ("Rekap Mingguan", "`/weekly_leaderboard` tersedia untuk semua anggota dan menampilkan aktivitas minggu berjalan.\n\nAdministrator dapat memakai `/weekly enable channel:#channel` untuk mengaktifkan rekap otomatis, `/weekly disable` untuk menghentikannya, dan `/weekly status` untuk memeriksa konfigurasi, channel, serta kondisi rekap. Rekap diproses ketika minggu baru dimulai. Jika channel tujuan hilang atau bot tidak dapat mengirim pesan, pilih channel yang valid lalu jalankan `/weekly enable` lagi."),
            "owner": ("Alat Owner Bot", "Perintah berikut hanya untuk owner bot, bukan administrator server biasa.\n\n`/owner backup_set channel:#channel`, `/owner backup_now`, `/owner restore_guide`, dan `/owner status` mengelola backup.\n`/recovery grant_user member:@Member amount:100 mode:add|set` dan `/recovery grant_mass role:@Role amount:100` adalah alat pemulihan XP.\n`/guilds` menampilkan guild yang diikuti bot."),
        }
        title, description = pages.get(topic, pages["main"])
        embed.title = title
        embed.description = description
        embed.set_footer(text="Gunakan /help dengan pilihan topik untuk membuka halaman lain.")
        return embed

    @app_commands.command(name="help", description="Lihat panduan penggunaan Jiromi.")
    @app_commands.describe(topik="Pilih bagian panduan.")
    @app_commands.choices(topik=[
        app_commands.Choice(name="Panduan utama", value="main"),
        app_commands.Choice(name="Aturan XP", value="user"),
        app_commands.Choice(name="Perintah member", value="profile"),
        app_commands.Choice(name="Mulai konfigurasi", value="setup"),
        app_commands.Choice(name="Kontrol XP", value="xp"),
        app_commands.Choice(name="Event", value="event"),
        app_commands.Choice(name="Placeholder event", value="placeholders"),
        app_commands.Choice(name="Rekap mingguan", value="weekly"),
        app_commands.Choice(name="Alat owner bot", value="owner"),
    ])
    async def help_command(self, interaction: discord.Interaction, topik: app_commands.Choice[str] = None):
        selected_topic = topik.value if topik else "main"
        await interaction.response.send_message(embed=self._get_embed(selected_topic), ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpSystem(bot, bot.db))
