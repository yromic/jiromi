# Panduan UX Perintah Jiromi

## Istilah yang digunakan

| Konsep | Istilah UI Indonesia | Pemakaian |
| --- | --- | --- |
| XP | XP | Tulis `XP`; jelaskan sebagai poin pengalaman saat konteks pertama memerlukannya. |
| Level | Level | Gunakan untuk tingkat kemajuan anggota. |
| Voice | Voice | Gunakan untuk aktivitas kanal suara Discord. |
| Cooldown | Jeda | Jelaskan sebagai waktu tunggu sebelum aktivitas dapat menghasilkan XP lagi. |
| Filter | Filter | Gunakan untuk aturan channel atau role yang menyertakan atau mengecualikan XP. |
| Recap | Rekap mingguan | Gunakan untuk ringkasan aktivitas mingguan. |
| Backup | Cadangan | Gunakan untuk salinan data dan pengaturan. |
| Status | Status | Selalu sertakan label teks yang menjelaskan keadaan. |

## Aturan salinan dan ikon

- Nama perintah dan nama opsi tidak memakai emoji dekoratif.
- Deskripsi perintah memakai teks biasa yang singkat dan jelas.
- Judul embed boleh memakai paling banyak satu ikon semantik bila membantu pemindaian.
- Baris isi dan bullet tidak memakai ikon dekoratif.
- Status selalu memakai label teks, misalnya `Aktif`, `Nonaktif`, `Perlu diperiksa`, atau `Gagal`; warna dan ikon tidak boleh menjadi satu-satunya penanda status.
- Medali peringkat dan karya lencana atau title yang sudah diperoleh tetap digunakan karena membawa makna produk.

## Penerapan pada permukaan UI

Tinjauan mencakup deskripsi slash command, pesan balasan, embed, tombol, select, tampilan timeout, dan tampilan progres pada cog profil, konfigurasi XP, event, setup, rekap mingguan, backup, pemulihan owner, bantuan, dan alat owner. Hapus ikon yang hanya mengulang kata di sekitarnya saat masing-masing permukaan diperbarui. Pertahankan medali peringkat, karya badge/title yang diperoleh, dan satu ikon status bila ikon tersebut menambah informasi di samping label teks.

## Respons interaksi

Gunakan `send_interaction_message` untuk respons awal atau followup ketika status acknowledgement belum diketahui. Gunakan `send_interaction_error` untuk pesan kesalahan yang dapat ditindaklanjuti. Pesan untuk pengguna tidak memuat exception, SQL, stack trace, atau detail internal; pemanggil mencatat konteks teknis melalui `bot.logger`.

Untuk view yang kedaluwarsa, nonaktifkan kontrol dan tambahkan satu pesan singkat: `Waktu habis. Kontrol dinonaktifkan.` Pertahankan isi konfigurasi atau progres yang sudah terlihat.
