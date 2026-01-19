#cogs/owner_backup.py

import discord
from discord import app_commands
from discord.ext import commands, tasks
import shutil
import os
import zipfile
import time
from datetime import datetime
import asyncio

# Menggunakan GroupCog (Saran Senior No. 8)
# Ini otomatis membuat semua command di dalamnya diawali "/owner"
class OwnerBackup(commands.GroupCog, name="owner"):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.last_backup_ts = 0  # Untuk Rate Limit (Saran No. 3)
        self.auto_backup_task.start()

    def cog_unload(self):
        self.auto_backup_task.cancel()

    # --- 1. STATIC CHECK (Saran Senior No. 1) ---
    # Diubah jadi staticmethod agar aman dari bug decorator
    @staticmethod
    async def is_bot_owner(interaction: discord.Interaction) -> bool:
        return await interaction.client.is_owner(interaction.user)

    # --- LOGIC INTI BACKUP ---
    async def perform_backup_logic(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_folder = "backups"
        if not os.path.exists(backup_folder): os.makedirs(backup_folder)

        temp_db_name = f"{backup_folder}/schema_backup_{timestamp}.db"
        zip_name = f"{backup_folder}/backup_{timestamp}.zip"

        try:
            # [FIX] Gunakan SQLite Online Backup via SQL
            # Ini aman dilakukan walau DB sedang jalan (WAL Mode support)
            await self.db.execute(f"VACUUM INTO '{temp_db_name}'")

            # Kompresi ZIP
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(temp_db_name, arcname="schema.db")
            
            # Ambil Metadata (Saran Senior No. 6)
            file_size = os.path.getsize(zip_name) / 1024 # KB
            guild_count = len(self.bot.guilds)
            user_count = await self.db.get_total_users() # Data dari DB handler
            
            metadata = {
                "size_kb": f"{file_size:.2f}",
                "guilds": guild_count,
                "users": user_count,
                "timestamp": timestamp
            }
            
            return zip_name, temp_db_name, metadata
            
        except Exception as e:
            print(f"❌ Backup Error di Logic: {e}")
            # Hapus file sampah jika error di tengah jalan
            if os.path.exists(temp_db_name): os.remove(temp_db_name)
            if os.path.exists(zip_name): os.remove(zip_name)
            return None, None, str(e)

    # --- COMMANDS ---

    @app_commands.command(name="backup_set", description="Set channel tujuan untuk pengiriman backup.")
    @app_commands.describe(channel="Channel private khusus backup")
    @app_commands.check(is_bot_owner)
    async def set_backup_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.db.set_bot_setting("backup_channel_id", channel.id)
        await interaction.response.send_message(
            f"✅ **Setup Berhasil.** Backup akan dikirim ke {channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(name="backup_now", description="Trigger backup manual (Cooldown 10 menit).")
    @app_commands.check(is_bot_owner)
    async def manual_backup(self, interaction: discord.Interaction):
        # Rate Limit Check (Saran Senior No. 3)
        now = time.time()
        cooldown = 600 # 10 menit
        if now - self.last_backup_ts < cooldown:
            remaining = int(cooldown - (now - self.last_backup_ts))
            return await interaction.response.send_message(
                f"⏳ **Cooldown.** Tunggu {remaining} detik lagi.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        
        # Cek Channel
        channel_id = await self.db.get_bot_setting("backup_channel_id")
        if not channel_id:
            return await interaction.followup.send("❌ Channel backup belum diset.")

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return await interaction.followup.send("❌ Channel backup hilang/tidak akses.")

        # Eksekusi
        zip_path, temp_db, meta = await self.perform_backup_logic()
        
        if zip_path and isinstance(meta, dict):
            # Update timestamp rate limit
            self.last_backup_ts = time.time()
            
            embed = discord.Embed(
                title="📦 Manual Database Backup",
                description=f"Backup user-triggered pada {discord.utils.format_dt(datetime.now())}",
                color=discord.Color.green()
            )
            # Embed Metadata (Saran Senior No. 6)
            embed.add_field(name="Size", value=f"{meta['size_kb']} KB", inline=True)
            embed.add_field(name="Data Scope", value=f"{meta['guilds']} Servers | {meta['users']} Users", inline=True)
            
            file = discord.File(zip_path)
            await channel.send(embed=embed, file=file)
            
            os.remove(zip_path)
            os.remove(temp_db)
            await interaction.followup.send("✅ Sukses.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Gagal: {meta}", ephemeral=True)

    @app_commands.command(name="restore_guide", description="Panduan cara restore database.")
    @app_commands.check(is_bot_owner)
    async def restore_guide(self, interaction: discord.Interaction):
        # SOP Restore (Saran Senior No. 7)
        msg = (
            "**🛠️ SOP RESTORE DATABASE**\n"
            "1. Download file `.zip` terbaru dari channel backup.\n"
            "2. Extract file tersebut, kamu akan dapat `schema.db`.\n"
            "3. Matikan bot (Stop Terminal).\n"
            "4. Buka folder `database/` di VPS/PC.\n"
            "5. **Rename** `schema.db` yang lama jadi `schema_old.db` (Buat jaga-jaga).\n"
            "6. Paste `schema.db` hasil extract tadi ke folder `database/`.\n"
            "7. Nyalakan bot kembali.\n"
            "8. Cek `/owner status` untuk memastikan DB terbaca."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="status", description="Cek status sistem backup.")
    @app_commands.check(is_bot_owner)
    async def backup_status(self, interaction: discord.Interaction):
        channel_id = await self.db.get_bot_setting("backup_channel_id")
        status = "✅ Aktif" if self.auto_backup_task.is_running() else "❌ Mati"
        
        # Hitung next run
        next_run = self.auto_backup_task.next_iteration
        next_run_str = discord.utils.format_dt(next_run, style="R") if next_run else "N/A"

        embed = discord.Embed(title="🛡️ Backup System Status", color=discord.Color.blue())
        embed.add_field(name="Auto Loop", value=status, inline=True)
        embed.add_field(name="Next Run", value=next_run_str, inline=True)
        embed.add_field(name="Channel ID", value=str(channel_id), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- AUTO LOOP ---
    @tasks.loop(hours=24)
    async def auto_backup_task(self):
        channel_id = await self.db.get_bot_setting("backup_channel_id")
        if not channel_id: return

        channel = self.bot.get_channel(int(channel_id))
        if not channel: return

        zip_path, temp_db, meta = await self.perform_backup_logic()
        
        if zip_path and isinstance(meta, dict):
            embed = discord.Embed(
                title="🔄 Auto-Backup Daily",
                description="Backup rutin otomatis.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Size", value=f"{meta['size_kb']} KB", inline=True)
            embed.add_field(name="Stats", value=f"{meta['guilds']} Guilds | {meta['users']} Users", inline=True)

            file = discord.File(zip_path)
            await channel.send(embed=embed, file=file)
            
            os.remove(zip_path)
            os.remove(temp_db)
        else:
            # Failure Notification (Saran Senior No. 5)
            # Jika gagal, bot akan mencoba lapor ke channel backup
            try:
                await channel.send(f"⚠️ **CRITICAL: AUTO-BACKUP GAGAL!**\nError: `{meta}`\nSegera cek console VPS.")
            except:
                print("Gagal mengirim notifikasi error backup.")

    # Safe Loop Start (Saran Senior No. 2)
    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

    # Error Handler
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("⛔ **Restricted Access.**", ephemeral=True)

async def setup(bot):
    await bot.add_cog(OwnerBackup(bot, bot.db))