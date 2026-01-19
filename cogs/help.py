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
        # 🟢 1. MAIN MENU
        if topic == "main":
            embed.title = "👋 Halo! Aku Jiromi 🤖"
            embed.description = (
                "Aku hadir untuk membuat server ini lebih hidup dengan Leveling & Event otomatis.\n"
                "Silakan pilih panduan sesuai kebutuhanmu:\n\n"
                
                "👤 **PANDUAN MEMBER**\n"
                "• `/help topic:user` — Cara mendapatkan XP & aturan main.\n"
                "• `/help topic:profile` — Cek Level & Leaderboard.\n"
                "• `/help topic:leveling` — Penjelasan sistem level.\n\n"
                
                "🛠️ **PANDUAN ADMIN**\n"
                "• `/help topic:quickstart` — **Mulai di sini (Setup Cepat).**\n"
                "• `/help topic:setup-wizard` — Konfigurasi otomatis via menu.\n"
                "• `/help topic:event` — Penjelasan Welcome/Leave/Ban.\n"
                "• `/help topic:event-commands` — Daftar perintah Event lengkap."
            )
            embed.set_footer(text="Pilih topik spesifik di command /help untuk detailnya.")

        # 👤 2. USER GUIDE
        elif topic == "user":
            embed.title = "👤 User Guide — Cara Dapat XP"
            embed.description = (
                "Ingin naik level? Berikut caranya:\n\n"
                "**💬 Chat XP**\n"
                "• Kirim pesan di channel teks.\n"
                "• **Syarat:** Minimal 8 karakter per pesan.\n"
                "• **Cooldown:** XP masuk setiap 10 detik sekali (Anti-Spam).\n\n"
                
                "**🎙️ Voice XP**\n"
                "• Gabung ke Voice Channel.\n"
                "• **Syarat:** Harus ada minimal 2 orang (bukan bot).\n"
                "• **Penting:** Jangan Self-Mute atau Deafen, atau XP tidak jalan!\n\n"
                
                "✨ *Tips: Aktiflah secara wajar, spamming justru tidak akan memberikan XP.*"
            )

        # 🏆 3. PROFILE COMMANDS
        elif topic == "profile":
            embed.title = "🏆 Profil & Rank"
            embed.description = (
                "Gunakan perintah ini untuk melihat pencapaianmu:\n\n"
                "**1. Cek Profil Sendiri/Orang Lain**\n"
                "`/rank` atau `/rank member:@User`\n"
                "*(Melihat level, total XP, dan durasi voice)*\n\n"
                
                "**2. Cek Peringkat Server**\n"
                "`/leaderboard`\n"
                "*(Melihat Top 5 Member dengan XP tertinggi)*\n\n"
                
                "**3. Cek Peringkat Mingguan**\n"
                "`/weekly_leaderboard`\n"
                "*(Siapa yang paling aktif minggu ini?)*"
            )

        # 🟢 2. QUICKSTART
        # 🚀 5. QUICKSTART (ADMIN)
        elif topic == "quickstart":
            embed.title = "🚀 Quick Start (Admin)"
            embed.description = (
                "Admin baru? Ikuti 3 langkah ini agar bot siap pakai:\n\n"
                "**1️⃣ Setup Dasar (Leveling & Notif)**\n"
                "Gunakan Setup Wizard untuk pengaturan cepat:\n"
                "`/setup` → *Ikuti langkah-langkah di layar.*\n\n"
                
                "**2️⃣ Setup Pesan Sambutan (Welcome)**\n"
                "Arahkan pesan selamat datang ke channel tertentu:\n"
                "`/event setup welcome #channel-tujuan`\n\n"
                
                "**3️⃣ Test Bot**\n"
                "Pastikan semua berjalan lancar:\n"
                "`/event test welcome`"
            )

        # 🧙‍♂️ 6. SETUP WIZARD
        elif topic == "setup-wizard":
            embed.title = "🧙‍♂️ Setup Wizard"
            embed.description = (
                "**Apa itu Setup Wizard?**\n"
                "Fitur interaktif untuk mengatur konfigurasi bot tanpa mengetik banyak command manual.\n\n"
                "**Cara Pakai:**\n"
                "Ketik `/setup` lalu pilih opsi di menu yang muncul.\n\n"
                "**Apa yang diatur?**\n"
                "✅ Channel Pengumuman Level Up\n"
                "✅ Mode Notifikasi (Quiet/Balanced/Loud)\n"
                "✅ Rate XP (Berapa XP per chat/menit)\n"
                "✅ Minimal user di Voice Channel"
            )
        
        # 📊 4. LEVELING EXPLANATION
        elif topic == "leveling":
            embed.title = "📊 Tentang Sistem Leveling"
            embed.description = (
                "**Bagaimana XP dihitung?**\n"
                "Sistem kami menggunakan kurva kesulitan. Semakin tinggi levelmu, "
                "semakin banyak XP yang dibutuhkan untuk naik ke level berikutnya.\n\n"
                
                "**Kenapa XP saya tidak masuk?**\n"
                "1. Pesanmu terlalu pendek (< 8 huruf).\n"
                "2. Kamu mengirim pesan terlalu cepat (kena cooldown 10s).\n"
                "3. Kamu sendirian di Voice Channel (butuh temen ngobrol!).\n"
                "4. Kamu sedang Mute/Deafen di Voice.\n\n"
                
                "**Hadiah (Rewards):**\n"
                "Pada level tertentu, kamu mungkin akan mendapatkan **Role Spesial** "
                "secara otomatis. Cek `/rank` untuk melihat progresmu!"
            )

        # 🟡 3. EVENT SYSTEM
        # 📣 7. EVENT SYSTEM OVERVIEW
        elif topic == "event":
            embed.title = "📣 Event System Overview"
            embed.description = (
                "Jiromi bisa menyapa user atau memberi info otomatis untuk 4 kejadian:\n"
                "**Welcome, Leave, Ban, & Nitro Boost**.\n\n"
                "**🔄 Alur Konfigurasi (Workflow):**\n"
                "1. **Setup** → Tentukan channel tujuannya (`/event setup`).\n"
                "2. **Content** → Atur isi pesannya (`/event message` atau `/event embed`).\n"
                "3. **Image** → Tambahkan gambar jika perlu (`/event image`).\n"
                "4. **Toggle** → Nyalakan/Matikan fiturnya (`/event toggle`).\n"
                "5. **Test** → Coba kirim pesan simulasi (`/event test`)."
            )
            embed.set_footer(text="Gunakan /event show [tipe] untuk melihat status saat ini.")

        # 🛠️ 8. EVENT COMMANDS LIST
        elif topic == "event-commands":
            embed.title = "🛠️ Daftar Command Event"
            embed.description = (
                "Berikut adalah daftar lengkap perintah untuk mengatur Event:\n\n"
                "`/event setup [tipe] [channel]`\n"
                "→ Mengaktifkan event dan memilih channel tujuan.\n\n"
                
                "`/event toggle [tipe] [ON/OFF]`\n"
                "→ Menyalakan atau mematikan event tanpa menghapus setting.\n\n"
                
                "`/event message [tipe] [teks]`\n"
                "→ Mengatur pesan teks biasa (bisa pakai {member}, {server}).\n\n"
                
                "`/event embed [tipe] ...`\n"
                "→ Mengaktifkan tampilan Embed (kotak berwarna).\n\n"
                
                "`/event image [tipe] [url]`\n"
                "→ Mengatur gambar background/GIF untuk embed.\n\n"
                
                "`/event show [tipe]`\n"
                "→ Melihat konfigurasi yang sedang aktif saat ini."
            )

        # 🔵 4. PLACEHOLDERS
        # 🔤 9. PLACEHOLDERS
        elif topic == "placeholders":
            embed.title = "🔤 Dynamic Placeholders"
            embed.description = (
                "Gunakan variabel ini agar pesanmu berubah otomatis sesuai konteks.\n\n"
                "**Daftar Variabel:**\n"
                "• `{member}` → Mention user (contoh: @Udin)\n"
                "• `{username}` → Nama user (contoh: Udin)\n"
                "• `{server}` → Nama server\n"
                "• `{member_count}` → Total member server\n"
                "• `{boost_count}` → Total Nitro Boost\n\n"
                
                "**Contoh Kalimat Real:**\n"
                "✅ *Welcome:*\n"
                "`Halo {member}, selamat datang di {server}! Kamu adalah member ke-{member_count}.`\n"
                "✅ *Leave:*\n"
                "`Yah, {username} telah meninggalkan kita.`\n\n"
                
                "⚠️ **Peringatan Format:**\n"
                "1. Gunakan kurung kurawal `{}` dengan huruf kecil semua.\n"
                "2. Jangan ada spasi di dalam kurung (salah: `{ member }`)."
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
        # 📷 11. IMAGE GUIDE
        elif topic == "image":
            embed.title = "📷 Panduan Gambar & GIF"
            embed.description = (
                "Kamu bisa memasang banner atau GIF bergerak di dalam Embed.\n\n"
                "**Cara Pakai:**\n"
                "`/event image [tipe] [url]`\n\n"
                
                "**⚠️ Syarat Wajib: Direct Link**\n"
                "Link harus berakhiran ekstensi file gambar seperti `.jpg`, `.png`, atau `.gif`.\n\n"
                "✅ **Benar:** `https://i.imgur.com/abcde.gif`\n"
                "❌ **Salah:** `https://imgur.com/gallery/abcde` (Ini link web)\n\n"
                "**Solusi jika gambar tidak muncul:**\n"
                "1. Cek apakah link bisa dibuka di browser.\n"
                "2. Pastikan bukan link Google Drive/Dropbox (sering bermasalah)."
            )

        # ⚙️ 12. XP ADMIN (LEVELING CONTROL)
        elif topic == "xp-admin":
            embed.title = "⚙️ Leveling Admin Controls"
            embed.description = (
                "Pusat kontrol untuk sistem XP dan Leveling.\n\n"
                "**Command Utama:**\n"
                "• `/xp setup`\n"
                "→ Mengatur channel notifikasi level up & rate XP (berapa XP per chat/menit).\n\n"
                "• `/xp announcement`\n"
                "→ **Quiet:** Tidak ada notifikasi.\n"
                "→ **Balanced:** Notifikasi HANYA jika dapat Role Reward (Recommended).\n"
                "→ **Loud:** Notifikasi setiap naik level.\n\n"
                "• `/xp status`\n"
                "→ Cek konfigurasi saat ini (apakah sistem jalan/mati, daftar reward, dll)."
            )

        # 🛡️ 13. XP FILTERS
        elif topic == "xp-filters":
            embed.title = "🛡️ XP Filters (Whitelist & Blacklist)"
            embed.description = (
                "Atur siapa dan di mana XP bisa didapatkan.\n\n"
                "**🎭 Filter Role:**\n"
                "• `/xp role allow @role` → Hanya role ini yang dapat XP (Whitelist).\n"
                "• `/xp role disallow @role` → Role ini DILARANG dapat XP (Blacklist).\n\n"
                "**📺 Filter Channel:**\n"
                "• `/xp channel allow #channel` → XP hanya jalan di channel ini.\n"
                "• `/xp channel disallow #channel` → XP mati di channel ini.\n\n"
                "**Use Case Umum:**\n"
                "*\"Saya ingin XP chat hanya jalan di #general dan #spam, tapi tidak di #serius.\"*\n"
                "👉 Gunakan `/xp channel allow` di kedua channel tersebut.\n\n"
                "**Reset:** Gunakan `/xp filter reset` untuk menghapus semua aturan."
            )

        # 🎁 14. XP REWARDS
        elif topic == "xp-rewards":
            embed.title = "🎁 XP Rewards (Hadiah Role)"
            embed.description = (
                "Berikan role otomatis saat member mencapai level tertentu.\n\n"
                "**Commands:**\n"
                "• `/xp reward add level:5 role:@Junior`\n"
                "• `/xp reward list` (Lihat daftar hadiah)\n\n"
                "**⚠️ SYARAT WAJIB (Penting):**\n"
                "Agar bot bisa memberikan role, pastikan **Role Bot (Jiromi)** berada **DI ATAS** role hadiah di pengaturan Server > Roles.\n\n"
                "**Tips:**\n"
                "Buatlah reward bertahap (Level 5, 10, 20, 50) agar member semangat mengejar rank!"
            )

        # ⚠️ 15. XP DANGER ZONE
        elif topic == "xp-danger":
            embed.title = "⚠️ XP Danger Zone (Reset Data)"
            embed.description = (
                "Hati-hati! Command di bawah ini bersifat destruktif dan **tidak bisa dibatalkan**.\n\n"
                "**☢️ Reset Server:**\n"
                "`/xp reset`\n"
                "→ Menghapus XP & Level milik **SEMUA MEMBER** di server ini kembali ke 0.\n\n"
                
                "**👤 Reset Personal:**\n"
                "`/xp reset_user @Member`\n"
                "→ Menghapus XP milik satu orang saja.\n\n"
                
                "**🛑 PERINGATAN PENTING:**\n"
                "Reset XP hanya menghapus angka di database. Bot **TIDAK** akan mencabut Role Reward yang sudah terlanjur didapatkan member secara otomatis.\n"
                "👉 *Admin harus mencabut role tersebut secara manual jika diperlukan.*"
            )
            embed.color = discord.Color.red() # Warna merah biar seram

        # 🔴 7. PERMISSIONS
        # 🔐 16. PERMISSIONS
        elif topic == "permissions":
            embed.title = "🔐 Permissions & Security"
            embed.description = (
                "Agar Jiromi berjalan lancar, pastikan bot memiliki izin berikut:\n\n"
                "**1. Izin Wajib (Minimum):**\n"
                "✅ `View Channels` & `Send Messages` (Untuk interaksi dasar)\n"
                "✅ `Embed Links` (Untuk tampilan kotak profil/event)\n"
                "✅ `Attach Files` (Untuk fitur backup database)\n"
                "✅ `Manage Roles` (KHUSUS untuk fitur XP Rewards)\n\n"
                
                "**2. Aturan Hierarki Role (Penting!):**\n"
                "Discord melarang bot memberikan role yang posisinya lebih tinggi darinya.\n"
                "👉 **Solusi:** Buka *Server Settings > Roles*, lalu geser role **Jiromi** ke posisi **DI ATAS** role hadiah (reward).\n\n"
                
                "**3. Channel Overrides:**\n"
                "Jika bot tidak merespon di channel tertentu, cek pengaturan permission channel tersebut. Pastikan bot tidak di-deny aksesnya."
            )
        
        # 🧠 17. TROUBLESHOOTING
        elif topic == "troubleshoot":
            embed.title = "🧠 Troubleshooting Checklist"
            embed.description = (
                "Bot bermasalah? Cek daftar ini sebelum panik:\n\n"
                "**A. Event (Welcome/Leave) Tidak Muncul**\n"
                "1. Cek `/event show [tipe]` → Pastikan Status **AKTIF**.\n"
                "2. Cek Channel ID → Apakah channel tujuan masih ada/benar?\n"
                "3. Cek Izin Bot → Bisakah bot kirim pesan di channel itu?\n\n"
                
                "**B. XP Tidak Bertambah**\n"
                "1. Cek `/xp status` → Pastikan sistem XP menyala.\n"
                "2. Cek Filter → Apakah channel/role masuk blacklist?\n"
                "3. Cek Aturan → Minimal 8 huruf (chat) atau 2 orang (voice).\n\n"
                
                "**C. Reward Role Tidak Masuk**\n"
                "1. Cek `/xp reward list` → Pastikan config benar.\n"
                "2. **HIERARKI ROLE** → Ini penyebab 99% masalah. Geser role bot ke atas!"
            )

        # ❓ 18. FAQ (FINAL)
        elif topic == "faq":
            embed.title = "❓ FAQ — Pertanyaan Umum"
            embed.description = (
                "**Q: Kenapa XP saya diam saja?**\n"
                "A: Mungkin kena cooldown (10 detik), pesan terlalu pendek, atau kamu sendirian di Voice Channel.\n\n"
                
                "**Q: Kenapa Welcome Message tidak ada gambarnya?**\n"
                "A: Link gambar salah. Harus Direct Link (ujungnya .jpg/.png/.gif). Jangan pakai link Google Drive.\n\n"
                
                "**Q: Kenapa Bot Offline / Tidak Merespon?**\n"
                "A: Bot ini berjalan di PC pribadi Owner (Local Host). Jika PC mati/internet putus, bot juga tidur.\n\n"
                
                "**Q: Apakah bot ini aman?**\n"
                "A: Aman. Bot hanya membaca pesan untuk menghitung XP dan tidak menyimpan isi chat member."
            )

        return embed

    @app_commands.command(name="help", description="Lihat panduan lengkap penggunaan Jiromi.")
    @app_commands.describe(topik="Pilih topik bantuan yang ingin dibaca")
    @app_commands.choices(topik=[
        # --- GENERAL ---
        app_commands.Choice(name="🏠 Main Menu", value="main"),
        
        # --- USER GUIDE ---
        app_commands.Choice(name="👤 User Guide (Cara Dapat XP)", value="user"),
        app_commands.Choice(name="🏆 Profile & Rank", value="profile"),
        app_commands.Choice(name="📊 Info Leveling System", value="leveling"),
        
        # --- ADMIN GUIDE: SETUP & EVENT ---
        app_commands.Choice(name="🚀 Quick Start (Admin)", value="quickstart"),
        app_commands.Choice(name="🧙‍♂️ Setup Wizard", value="setup-wizard"),
        app_commands.Choice(name="📣 Event System Overview", value="event"),
        app_commands.Choice(name="🛠️ Event Commands List", value="event-commands"),
        
        # --- ADMIN GUIDE: LEVELING CONTROL ---
        app_commands.Choice(name="⚙️ XP Admin (Setup & Status)", value="xp-admin"),
        app_commands.Choice(name="🛡️ XP Filters (Role & Channel)", value="xp-filters"),
        app_commands.Choice(name="🎁 XP Rewards (Hadiah Role)", value="xp-rewards"),
        app_commands.Choice(name="⚠️ XP Danger Zone (Reset)", value="xp-danger"), # <--- BARU
        
        # --- TECHNICAL & HELP ---
        app_commands.Choice(name="🔐 Permissions & Security", value="permissions"), # <--- UPDATE
        app_commands.Choice(name="🧠 Troubleshooting", value="troubleshoot"), # <--- BARU
        app_commands.Choice(name="❓ FAQ", value="faq"),
        
        # --- EXTRAS ---
        app_commands.Choice(name="🔤 Placeholders", value="placeholders"),
        app_commands.Choice(name="🖼️ Panduan Embed", value="embed"),
        app_commands.Choice(name="📷 Panduan Gambar", value="image"),
    ])

    async def help_command(self, interaction: discord.Interaction, topik: app_commands.Choice[str] = None):
        # Default ke halaman utama jika tidak memilih topik
        selected_topic = topik.value if topik else "main"
        
        embed = self._get_embed(selected_topic)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    # db passed but not used widely in help, kept for consistency
    await bot.add_cog(HelpSystem(bot, bot.db))
