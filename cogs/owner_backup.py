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
import aiosqlite

# Menggunakan GroupCog (Saran Senior No. 8)
# Ini otomatis membuat semua command di dalamnya diawali "/owner"
class OwnerBackup(commands.GroupCog, name="owner"):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.last_backup_ts = 0

    async def cog_load(self):
        """Dipanggil saat Cog berhasil dimuat sepenuhnya oleh bot."""
        self.auto_backup_task.start()

    def cog_unload(self):
        self.auto_backup_task.cancel()

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
            # 1. Tahap Replikasi (VACUUM INTO) - Koneksi Privat
            real_db_path = self.db.db_path
            async with aiosqlite.connect(real_db_path) as backup_conn:
                await backup_conn.execute(f"VACUUM INTO '{temp_db_name}'")

            # 2. Quality Control
            # A. Sanity Check
            if os.path.getsize(temp_db_name) < 1024:
                raise RuntimeError("Backup gagal: Ukuran file terlalu kecil.")

            # B. Integrity Check
            async with aiosqlite.connect(temp_db_name) as check_db:
                async with check_db.execute("PRAGMA integrity_check;") as cursor:
                    row = await cursor.fetchone()
                    if not row or row[0] != "ok":
                        raise RuntimeError(f"Backup korup: {row[0] if row else 'Unknown'}")

            # 3. Zip & Metadata
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(temp_db_name, arcname="schema.db")
            
            file_size = os.path.getsize(zip_name) / 1024 
            guild_count = len(self.bot.guilds)
            try:
                user_count = await self.db.get_total_users()
            except:
                user_count = "N/A"
            
            metadata = {
                "size_kb": f"{file_size:.2f}",
                "guilds": guild_count,
                "users": user_count,
                "timestamp": timestamp,
                "verified": True
            }
            
            # [FIX LOGIC] Hapus temp_db di sini saja. Jangan bawa keluar.
            if os.path.exists(temp_db_name): os.remove(temp_db_name)
            
            # [FIX RETURN] Cukup return Zip dan Meta. Temp DB sudah musnah.
            return zip_name, metadata
            
        except Exception as e:
            print(f"❌ CRITICAL BACKUP ERROR: {e}")
            if os.path.exists(temp_db_name): os.remove(temp_db_name)
            if os.path.exists(zip_name): os.remove(zip_name)
            
            # Return 2 value (None, ErrorMsg)
            return None, str(e)

    @app_commands.command(name="backup_set", description="Set channel tujuan untuk pengiriman backup.")
    @app_commands.describe(channel="Channel private khusus backup")
    @app_commands.check(is_bot_owner)
    async def set_backup_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.db.set_bot_setting("backup_channel_id", channel.id)
        await interaction.response.send_message(
            f"[PROCESS]  **Setup Berhasil.** Backup akan dikirim ke {channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(name="backup_now", description="Trigger backup manual (Cooldown 10 menit).")
    @app_commands.check(is_bot_owner)
    async def manual_backup(self, interaction: discord.Interaction):
        # Rate Limit Check
        now = time.time()
        cooldown = 600 # 10 menit
        if now - self.last_backup_ts < cooldown:
            remaining = int(cooldown - (now - self.last_backup_ts))
            return await interaction.response.send_message(
                f"[PROCESS] **Cooldown.** Tunggu {remaining} detik lagi.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        
        channel_id = await self.db.get_bot_setting("backup_channel_id")
        if not channel_id:
            return await interaction.followup.send("❌ Channel backup belum diset.")

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return await interaction.followup.send("❌ Channel backup hilang/tidak akses.")

        # [FIX CRITICAL] Unpacking 2 Value
        zip_path, meta = await self.perform_backup_logic()
        
        if zip_path and isinstance(meta, dict):
            # [FIX MAJOR] Update Timestamp agar cooldown jalan!
            self.last_backup_ts = time.time()
            
            embed = discord.Embed(
                title="📦 Manual Database Backup",
                description=f"Backup user-triggered pada {discord.utils.format_dt(datetime.now())}",
                color=discord.Color.green()
            )
            embed.add_field(name="Size", value=f"{meta['size_kb']} KB", inline=True)
            embed.add_field(name="Data Scope", value=f"{meta['guilds']} Servers | {meta['users']} Users", inline=True)
            
            file = discord.File(zip_path)
            await channel.send(embed=embed, file=file)
            
            os.remove(zip_path)
            await interaction.followup.send("[SUCCESS] Sukses.", ephemeral=True)
        else:
            await interaction.followup.send(f"[FAILED] Gagal: {meta}", ephemeral=True)

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
        status = "[SUCCESS] Aktif" if self.auto_backup_task.is_running() else "❌ Mati"
        
        # Hitung next run
        next_run = self.auto_backup_task.next_iteration
        next_run_str = discord.utils.format_dt(next_run, style="R") if next_run else "N/A"

        embed = discord.Embed(title="🛡️ Backup System Status", color=discord.Color.blue())
        embed.add_field(name="Auto Loop", value=status, inline=True)
        embed.add_field(name="Next Run", value=next_run_str, inline=True)
        embed.add_field(name="Channel ID", value=str(channel_id), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- AUTO LOOP ---
    # --- AUTO LOOP ---
    @tasks.loop(hours=24)
    async def auto_backup_task(self):
        # 1. Skip jika ini iterasi pertama (Logic Skip First Run)
        # (Opsional: Jika kamu pakai logic skip first run, aktifkan ini. 
        # Jika pakai delay 60s, biarkan jalan terus tidak masalah)
        # if self._first_run:
        #    self._first_run = False
        #    return

        channel_id = await self.db.get_bot_setting("backup_channel_id")
        if not channel_id: return

        channel = self.bot.get_channel(int(channel_id))
        if not channel: return

        try:
            # [FIX CRITICAL] Unpacking HANYA 2 VALUE (Zip & Meta)
            # Hapus variable 'temp_db' dari sini
            zip_path, meta = await self.perform_backup_logic()
            
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
                
                # Cleanup Zip (Temp DB sudah bersih dari dalam fungsi logic)
                if os.path.exists(zip_path): os.remove(zip_path)
            
            else:
                # Error Handling (Meta berisi string error)
                error_msg = str(meta)
                # Ignore jika DB sibuk
                if "SQL statements in progress" in error_msg:
                    return

                try:
                    await channel.send(f"⚠️ **AUTO-BACKUP GAGAL!**\nError: `{error_msg}`")
                except:
                    pass

        except Exception as e:
            print(f"❌ Error Unhandled di Auto-Backup: {e}")

    # Safe Loop Start (Saran Senior No. 2 + Fix Lifecycle)
    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()
        # Delay ini WAJIB ada agar backup pertama tidak tabrakan sama startup
        print("[PROCESS] Auto-Backup: Menunggu startup stabil (60s)...")
        await asyncio.sleep(60)

    # Error Handler
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("⛔ **Restricted Access.**", ephemeral=True)

    # [FIX FINAL] Global Task Error Handler
    @auto_backup_task.error
    async def auto_backup_error(self, error):
        # Kita pakai print karena mungkin logger DB juga error
        print(f"🔥 CRITICAL: Auto-Backup Loop DIED. Error: {error}")
        # Jika punya logger, pakai juga:
        # self.bot.logger.error("BACKUP_LOOP_CRASH", "Backup loop died", error_obj=error)

async def setup(bot):
    await bot.add_cog(OwnerBackup(bot, bot.db))