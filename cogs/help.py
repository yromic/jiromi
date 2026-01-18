# cogs/help.py
import discord
from discord import app_commands
from discord.ext import commands

class HelpSystem(commands.Cog):
    def __init__(self, bot, db=None):
        # db bersifat opsional di sini karena help system hanya menampilkan teks statis
        self.bot = bot
        self.db = db

    def _get_embed(self, topic: str) -> discord.Embed:
        """Helper untuk membuat embed berdasarkan topik yang dipilih."""
        
        embed = discord.Embed(color=discord.Color.blue())
        
        # 🟢 1. MAIN MENU
        #  🟢  1. MAIN MENU
        if topic == "main":
            embed.title = " 👋  Halo! Aku Jiromi  🤖 "
            embed.description = (
                "Aku hadir untuk membantu server ini menjadi lebih hidup dengan fitur:\n"
                "•  📣  **Event Announcement** (Welcome, Leave, Ban, Boost)\n"
                "•  🎖️  **Leveling & Engagement** (Voice & Chat XP)\n\n"
                "** 📚  PANDUAN ADMIN**\n"
                "Pilih topik bantuan menggunakan menu command:\n\n"
                " 🚀  `/help topic:quickstart` — **Mulai Cepat (Wajib Baca)**\n"
                " 📊  `/help topic:leveling` — **Aturan XP & Setup Reward**\n"  # <--- BARIS BARU DITAMBAHKAN
                " 📣  `/help topic:event` — Penjelasan Welcome/Leave/Ban\n"
                " 🔤  `/help topic:placeholders` — Variabel {member}, {server}\n"
                " 🖼️  `/help topic:embed` — Mengatur tampilan & warna\n"
                " 📷  `/help topic:image` — Mengatur Gambar/GIF\n"
                " 🔐  `/help topic:permissions` — Hak akses bot\n"
                " ❓  `/help topic:faq` — Tanya Jawab Umum"
            )
            embed.set_footer(text="Pilih topik spesifik di command /help untuk detailnya.")

        # 🟢 2. QUICKSTART
        elif topic == "quickstart":
            embed.title = "🚀 QUICK START — Cara Menggunakan Jiromi"
            embed.description = (
                "Ingin fitur **Welcome** langsung jalan? Ikuti 4 langkah mudah ini:\n\n"
                "1️⃣ **Aktifkan & Pilih Channel**\n"
                "`/event setup welcome #channel-tujuan`\n"
                "*(Ganti #channel-tujuan dengan channel aslimu)*\n\n"
                "2️⃣ **Atur Pesan Sapaan**\n"
                "`/event message welcome Halo {member}, selamat datang di {server}!`\n\n"
                "3️⃣ **(Opsional) Aktifkan Tampilan Keren (Embed)**\n"
                "`/event embed welcome use_embed:True`\n\n"
                "4️⃣ **Test Hasilnya**\n"
                "`/event test welcome`\n\n"
                "🎉 **Selesai!**\n"
                "Sekarang setiap ada member baru, Jiromi akan menyapa mereka di channel tersebut."
            )
        
        elif topic == "leveling":
            embed.title = " 📊  SISTEM LEVELING & XP"
            embed.description = (
                "Pahami bagaimana XP dihitung agar levelmu cepat naik!\n\n"
                "** 💬  Aturan Chat XP:**\n"
                "• **Min. Panjang:** Pesan harus lebih dari **8 karakter**.\n"
                "• **Cooldown:** XP diberikan maksimal tiap **10 detik** sekali (anti-spam).\n"
                "• **Rate:** Default 5 XP per pesan valid.\n\n"
                "** 🎙️  Aturan Voice XP:**\n"
                "• **Syarat:** Harus ada minimal **2 orang** (bukan bot) di channel.\n"
                "• **Status:** Tidak boleh *Self-Mute* atau *Deafen*.\n"
                "• **Rate:** Default 10 XP per menit.\n\n"
                "** 🛠️  Setup Admin (Wajib):**\n"
                "1. `/xp setup` → Atur channel notifikasi & besar XP.\n"
                "2. `/xp role allow @role` → Izinkan role tertentu dapat XP.\n"
                "3. `/xp reward add` → Tambah hadiah kenaikan level.\n"
                "4. `/xp reward list` → **Lihat daftar hadiah yang aktif.**\n\n" # <--- BARIS BARU
                "⚠️ **PENTING:** Pastikan posisi Role Bot berada **DI ATAS** role reward di pengaturan Server > Roles."
            )

        # 🟡 3. EVENT SYSTEM
        elif topic == "event":
            embed.title = " 📣  EVENT ANNOUNCEMENT SYSTEM"
            embed.description = (
                "Jiromi mendukung 4 jenis event otomatis:\n\n"
                "1. **Welcome** — Saat member baru bergabung.\n"
                "2. **Leave** — Saat member keluar atau dikick.\n"
                "3. **Ban** — Saat member dibanned oleh admin.\n"
                "4. **Boost** — Saat member melakukan Nitro Boost.\n\n"
                " ⚙️  **Apa yang bisa diatur?**\n"
                "• **Cek Config:** Gunakan `/event show` untuk melihat setelan aktif.\n" # <--- BARIS BARU
                "• **Channel:** Set target via `/event setup`.\n"
                "• **Status:** Nyalakan/Matikan via `/event toggle`.\n"
                "• **Konten:** Atur pesan teks, embed, atau gambar background.\n"
                "• **Test:** Simulasikan tampilan via `/event test`."
            )
            embed.set_footer(text="Gunakan /event show [tipe] untuk melihat status saat ini.")

        # 🔵 4. PLACEHOLDERS
        elif topic == "placeholders":
            embed.title = "🔤 PLACEHOLDER (Variabel Otomatis)"
            embed.description = (
                "Gunakan kode ini agar pesan bot berubah otomatis sesuai data user.\n\n"
                "**Daftar Kode:**\n"
                "• `{member}` → Mention user (contoh: @User)\n"
                "• `{username}` → Nama user saja (contoh: Udin)\n"
                "• `{server}` → Nama server ini\n"
                "• `{member_count}` → Total member saat ini\n"
                "• `{boost_count}` → Total Nitro Boost saat ini\n\n"
                "**Contoh Penggunaan:**\n"
                "*\"Halo {member}, selamat datang di {server}! Kamu member ke-{member_count}.\"*\n\n"
                "⚠️ **Catatan Penting:**\n"
                "1. Hanya bekerja di **Pesan Teks** & **Deskripsi Embed**.\n"
                "2. **TIDAK** bisa dipakai di dalam URL Gambar/GIF.\n"
                "3. Penulisan harus huruf kecil semua & pakai kurung kurawal `{}`."
            )

        # 🟣 5. EMBED GUIDE
        elif topic == "embed":
            embed.title = "🖼️ PANDUAN EMBED (Pesan Kotak)"
            embed.description = (
                "Embed membuat pengumuman terlihat lebih rapi dan profesional.\n\n"
                "**Fitur Embed Jiromi:**\n"
                "• Judul & Deskripsi (Support placeholder)\n"
                "• Warna Sisi (Custom HEX Color)\n"
                "• Thumbnail Otomatis (Avatar member)\n"
                "• Image Utama (Gambar besar di bawah)\n\n"
                "🎨 **Cara Mengatur Warna (Hex Code):**\n"
                "• `0xFF0000` atau `#FF0000` → Merah 🔴\n"
                "• `0x00FF00` atau `#00FF00` → Hijau 🟢\n"
                "• `0x5865F2` atau `#5865F2` → Discord Blue 🔵\n\n"
                "**Perintah:**\n"
                "Gunakan `/event embed` untuk mengaktifkan dan mengatur isinya."
            )

        # 🟠 6. IMAGE GUIDE
        elif topic == "image":
            embed.title = "📷 PANDUAN GAMBAR & GIF"
            embed.description = (
                "Kamu bisa menambahkan gambar bergerak (GIF) atau statis di dalam Embed.\n\n"
                "✅ **Syarat Link Gambar:**\n"
                "1. Harus **Direct Link** (berakhiran `.jpg`, `.png`, atau `.gif`).\n"
                "2. Gunakan Giphy/Imgur atau Copy Link dari upload Discord.\n\n"
                "**Contoh Benar:**\n"
                "✅ `https://media.giphy.com/media/cat/giphy.gif`\n"
                "✅ `https://cdn.discordapp.com/attachments/.../image.png`\n\n"
                "**Contoh Salah (JANGAN DIPAKAI):**\n"
                "❌ `https://tenor.com/view/funny-gif-123` (Ini link web, bukan gambar!)\n"
                "❌ `C:/Users/Gambar/foto.jpg` (File lokal tidak bisa dibaca bot)\n\n"
                "**Cara Pasang:**\n"
                "Gunakan perintah `/event image`."
            )

        # 🔴 7. PERMISSIONS
        elif topic == "permissions":
            embed.title = "🔐 IZIN AKSES & KEAMANAN"
            embed.description = (
                "Demi keamanan server, konfigurasi Jiromi dibatasi.\n\n"
                "⛔ **Siapa yang bisa mengatur Jiromi?**\n"
                "Hanya user dengan izin **ADMINISTRATOR** server.\n\n"
                "**Jika muncul pesan \"Akses Ditolak\":**\n"
                "Artinya akun Discord-mu tidak memiliki hak akses Administrator.\n"
                "Silakan hubungi Owner Server untuk melakukan konfigurasi.\n\n"
                "*Member biasa tetap bisa melihat rank/level mereka, tapi tidak bisa mengubah setting bot.*"
            )

        # 🟤 8. FAQ (Revisi sesuai request)
        elif topic == "faq":
            embed.title = "❓ FAQ — Pertanyaan Umum"
            embed.description = (
                "**Q: Kenapa pesannya dobel (ada teks biasa DAN embed)?**\n"
                "A: Normal. Teks biasa untuk *mention* (@User), Embed untuk tampilan. Kosongkan teks pesan jika ingin full embed.\n\n"
                "**Q: Kenapa GIF tidak muncul?**\n"
                "A: Link salah. Pastikan link berakhiran `.gif` (Direct Link).\n\n"
                "**Q: Kenapa Welcome tidak muncul saat member masuk?**\n"
                "A: Cek `/event toggle` (harus ON), cek channel masih ada, dan cek izin bot di channel itu.\n\n"
                "**Q: Apakah bot ini online 24 Jam?**\n"
                "A: **Tidak selalu.** Bot ini dijalankan manual via script (VBS) di PC pribadi Owner. \n"
                "👉 **Bot Nyala = PC Owner Nyala.**\n"
                "*(Mohon maklum ya, belum ada budget buat sewa VPS/Cloud server 🙏)*"
            )

        return embed

    @app_commands.command(name="help", description="Lihat panduan lengkap penggunaan Jiromi.")
    @app_commands.describe(topik="Pilih topik bantuan yang ingin dibaca")
    @app_commands.choices(topik=[
        app_commands.Choice(name=" 🏠  Halaman Utama", value="main"),
        app_commands.Choice(name=" 🚀  Quick Start (Admin Baru)", value="quickstart"),
        app_commands.Choice(name=" 📊  Leveling & XP (Aturan Main)", value="leveling"), # <--- TAMBAHAN BARU
        app_commands.Choice(name=" 📣  Event System (Welcome/Leave)", value="event"),
        app_commands.Choice(name=" 🔤  Placeholders ({member})", value="placeholders"),
        app_commands.Choice(name=" 🖼️  Panduan Embed & Warna", value="embed"),
        app_commands.Choice(name=" 📷  Panduan Gambar & GIF", value="image"),
        app_commands.Choice(name=" 🔐  Permission & Akses", value="permissions"),
        app_commands.Choice(name=" ❓  FAQ (Tanya Jawab)", value="faq"),
    ])
    async def help_command(self, interaction: discord.Interaction, topik: app_commands.Choice[str] = None):
        # Default ke halaman utama jika tidak memilih topik
        selected_topic = topik.value if topik else "main"
        
        embed = self._get_embed(selected_topic)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    # db passed but not used widely in help, kept for consistency
    await bot.add_cog(HelpSystem(bot, bot.db))
