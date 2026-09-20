import asyncio
import os
import time
import zipfile
from datetime import datetime, timezone

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.interaction_responses import send_interaction_error, send_interaction_message
from utils.views import ExecutorView


class BackupChannelConfirmView(ExecutorView):
    def __init__(self, cog, author_id, channel):
        super().__init__(author_id=author_id, timeout=60)
        self.cog, self.channel = cog, channel

    @discord.ui.button(label="Simpan channel", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction, button):
        self.stop()
        await self.cog.db.set_bot_setting("backup_channel_id", self.channel.id)
        await interaction.response.edit_message(
            content=f"Channel backup disimpan: {self.channel.mention}. Backup otomatis akan dikirim ke sana saat jadwal berikutnya.",
            view=None,
        )

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content="Perubahan channel backup dibatalkan.", view=None)


class OwnerBackup(commands.GroupCog, name="owner"):
    def __init__(self, bot, db):
        self.bot, self.db = bot, db
        self.last_backup_ts = 0
        self.last_backup_result = None
        self.last_backup_at = None

    async def cog_load(self):
        self.auto_backup_task.start()

    def cog_unload(self):
        self.auto_backup_task.cancel()

    @staticmethod
    async def is_bot_owner(interaction: discord.Interaction) -> bool:
        return await interaction.client.is_owner(interaction.user)

    def _record_backup_result(self, result):
        self.last_backup_result = result
        self.last_backup_at = datetime.now(timezone.utc)

    async def perform_backup_logic(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_folder = "backups"
        os.makedirs(backup_folder, exist_ok=True)
        temp_db_name = os.path.join(backup_folder, f"schema_backup_{timestamp}.db")
        zip_name = os.path.join(backup_folder, f"backup_{timestamp}.zip")
        try:
            async with aiosqlite.connect(self.db.db_path) as backup_conn:
                await backup_conn.execute(f"VACUUM INTO '{temp_db_name}'")
            if os.path.getsize(temp_db_name) < 1024:
                raise RuntimeError("backup database unexpectedly small")
            async with aiosqlite.connect(temp_db_name) as check_db:
                async with check_db.execute("PRAGMA integrity_check;") as cursor:
                    row = await cursor.fetchone()
                    if not row or row[0] != "ok":
                        raise RuntimeError("backup database failed integrity check")
            with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(temp_db_name, arcname="schema.db")
            try:
                users = await self.db.get_total_users()
            except Exception as error:
                self.bot.logger.error("BACKUP_METADATA_FAIL", "Gagal menghitung metadata backup", error_obj=error)
                users = "tidak tersedia"
            return zip_name, {"size_kb": f"{os.path.getsize(zip_name) / 1024:.2f}", "guilds": len(self.bot.guilds), "users": users, "timestamp": timestamp}
        except Exception as error:
            self.bot.logger.error("BACKUP_CREATE_FAIL", "Gagal membuat backup database", error_obj=error)
            if os.path.exists(zip_name):
                os.remove(zip_name)
            return None, "Pembuatan backup gagal. Periksa log bot dan kesehatan database."
        finally:
            if os.path.exists(temp_db_name):
                try: os.remove(temp_db_name)
                except OSError as error: self.bot.logger.error("BACKUP_CLEANUP_FAIL", "Gagal menghapus database sementara", error_obj=error)

    @app_commands.command(name="backup_set", description="Pilih channel privat tujuan file backup.")
    @app_commands.describe(channel="Channel privat khusus backup")
    @app_commands.check(is_bot_owner)
    async def set_backup_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        existing = await self.db.get_bot_setting("backup_channel_id")
        if str(channel.id) == str(existing):
            await send_interaction_message(interaction, content=f"Backup sudah dikirim ke {channel.mention}.")
            return
        view = BackupChannelConfirmView(self, interaction.user.id, channel)
        prior = f" Channel sebelumnya: <#{existing}>." if existing else " Belum ada channel sebelumnya."
        await interaction.response.send_message(f"Simpan {channel.mention} sebagai tujuan backup?{prior}", ephemeral=True, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="backup_now", description="Buat dan kirim backup sekarang; jeda 10 menit per proses bot.")
    @app_commands.check(is_bot_owner)
    async def manual_backup(self, interaction: discord.Interaction):
        cooldown, now = 600, time.time()
        remaining = int(cooldown - (now - self.last_backup_ts))
        if remaining > 0:
            minutes, seconds = divmod(remaining, 60)
            await send_interaction_message(interaction, content=f"Backup manual tersedia lagi dalam {minutes} menit {seconds} detik.")
            return
        await interaction.response.defer(ephemeral=True)
        channel_id = await self.db.get_bot_setting("backup_channel_id")
        if not channel_id:
            await send_interaction_error(interaction, "Tujuan backup belum dipilih. Jalankan `/owner backup_set` dan pilih channel privat.")
            return
        channel = self.bot.get_channel(int(channel_id))
        if not isinstance(channel, discord.abc.Messageable):
            await send_interaction_error(interaction, "Channel backup tidak tersedia. Periksa akses bot lalu pilih ulang dengan `/owner backup_set`.")
            return
        zip_path, metadata = await self.perform_backup_logic()
        if not zip_path:
            self._record_backup_result("Gagal membuat file backup")
            await send_interaction_error(interaction, "File backup tidak dapat dibuat. Periksa log bot dan coba lagi.")
            return
        # Preserve the existing cooldown behaviour: a created backup starts the
        # cooldown even when the subsequent Discord upload is unavailable.
        self.last_backup_ts = time.time()
        try:
            embed = discord.Embed(title="Backup database manual", description=f"Dibuat {discord.utils.format_dt(datetime.now(timezone.utc), style='F')}", color=discord.Color.green())
            embed.add_field(name="Ukuran", value=f"{metadata['size_kb']} KB")
            embed.add_field(name="Cakupan", value=f"{metadata['guilds']} server | {metadata['users']} user")
            await channel.send(embed=embed, file=discord.File(zip_path))
        except discord.Forbidden as error:
            self.bot.logger.error("BACKUP_UPLOAD_FORBIDDEN", "Bot tidak dapat mengunggah backup ke channel", error_obj=error)
            self._record_backup_result("Gagal: bot tidak memiliki izin mengunggah file")
            await send_interaction_error(interaction, "Backup dibuat, tetapi bot tidak memiliki izin mengunggah file ke channel tujuan. Periksa izin Attach Files.")
            return
        except discord.HTTPException as error:
            self.bot.logger.error("BACKUP_UPLOAD_FAIL", "Gagal mengunggah backup", error_obj=error)
            self._record_backup_result("Gagal mengunggah file backup")
            await send_interaction_error(interaction, "Backup dibuat, tetapi pengiriman file gagal. Coba lagi dan periksa channel tujuan.")
            return
        finally:
            if os.path.exists(zip_path): os.remove(zip_path)
        self._record_backup_result(f"Terkirim ke #{getattr(channel, 'name', 'channel')}")
        await send_interaction_message(interaction, content=f"Backup berhasil dikirim ke {channel.mention}.")

    @app_commands.command(name="restore_guide", description="Lihat langkah aman untuk memulihkan database dari backup.")
    @app_commands.check(is_bot_owner)
    async def restore_guide(self, interaction: discord.Interaction):
        message = (
            "**Panduan pemulihan database**\n"
            "1. Unduh file `.zip` terbaru dari channel backup.\n"
            "2. Ekstrak hingga mendapatkan `schema.db`.\n"
            "3. Hentikan bot.\n"
            "4. Cadangkan database aktif dengan nama lain.\n"
            "5. Ganti database aktif dengan `schema.db` hasil ekstrak.\n"
            "6. Jalankan bot dan cek `/owner status`."
        )
        await send_interaction_message(interaction, content=message)

    @app_commands.command(name="status", description="Lihat tujuan, jadwal, dan hasil backup terbaru.")
    @app_commands.check(is_bot_owner)
    async def backup_status(self, interaction: discord.Interaction):
        channel_id = await self.db.get_bot_setting("backup_channel_id")
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        next_run = self.auto_backup_task.next_iteration
        cooldown_remaining = max(0, int(600 - (time.time() - self.last_backup_ts)))
        last_result = self.last_backup_result or "Belum ada hasil sejak bot dijalankan"
        last_time = discord.utils.format_dt(self.last_backup_at, style="R") if self.last_backup_at else "Belum ada"
        status = "Aktif" if self.auto_backup_task.is_running() else "Tidak aktif"
        destination = channel.mention if channel else ("Channel tersimpan tidak tersedia" if channel_id else "Belum dipilih")
        embed = discord.Embed(title="Status backup", color=discord.Color.blue())
        embed.add_field(name="Pengiriman otomatis", value=status, inline=False)
        embed.add_field(name="Tujuan", value=destination, inline=False)
        embed.add_field(name="Jadwal berikutnya", value=discord.utils.format_dt(next_run, style="R") if next_run else "Menunggu loop dimulai", inline=False)
        embed.add_field(name="Hasil terakhir sejak bot aktif", value=f"{last_result}\nWaktu: {last_time}", inline=False)
        embed.add_field(name="Backup manual", value=f"Tersedia sekarang" if cooldown_remaining == 0 else f"Tersedia lagi dalam {cooldown_remaining // 60} menit {cooldown_remaining % 60} detik", inline=False)
        await send_interaction_message(interaction, embed=embed)

    @tasks.loop(hours=24)
    async def auto_backup_task(self):
        channel_id = await self.db.get_bot_setting("backup_channel_id")
        if not channel_id: return
        channel = self.bot.get_channel(int(channel_id))
        if not isinstance(channel, discord.abc.Messageable):
            self._record_backup_result("Gagal: channel tujuan tidak tersedia")
            self.bot.logger.error("BACKUP_CHANNEL_UNAVAILABLE", "Channel backup tidak tersedia")
            return
        zip_path, metadata = await self.perform_backup_logic()
        if not zip_path:
            self._record_backup_result("Gagal membuat file backup")
            return
        try:
            embed = discord.Embed(title="Backup database otomatis", description="Backup rutin otomatis.", color=discord.Color.gold())
            embed.add_field(name="Ukuran", value=f"{metadata['size_kb']} KB")
            embed.add_field(name="Cakupan", value=f"{metadata['guilds']} server | {metadata['users']} user")
            await channel.send(embed=embed, file=discord.File(zip_path))
            self._record_backup_result(f"Terkirim ke #{getattr(channel, 'name', 'channel')}")
        except discord.Forbidden as error:
            self.bot.logger.error("BACKUP_UPLOAD_FORBIDDEN", "Bot tidak dapat mengunggah backup otomatis", error_obj=error)
            self._record_backup_result("Gagal: bot tidak memiliki izin mengunggah file")
        except discord.HTTPException as error:
            self.bot.logger.error("BACKUP_UPLOAD_FAIL", "Gagal mengunggah backup otomatis", error_obj=error)
            self._record_backup_result("Gagal mengunggah file backup")
        finally:
            if os.path.exists(zip_path): os.remove(zip_path)

    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await send_interaction_error(interaction, "Perintah ini hanya dapat digunakan oleh owner bot.")

    @auto_backup_task.error
    async def auto_backup_error(self, error):
        self._record_backup_result("Loop backup berhenti karena kesalahan")
        self.bot.logger.error("BACKUP_LOOP_CRASH", "Loop backup berhenti", error_obj=error)


async def setup(bot):
    await bot.add_cog(OwnerBackup(bot, bot.db))
