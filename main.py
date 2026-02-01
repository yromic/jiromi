import discord
from discord.ext import commands
import os
import asyncio
import sys # [TAMBAHAN] Untuk exit system yang bersih
from dotenv import load_dotenv  
from utils.db_handler import init_db, close_db
from utils.logger import JiromiLogger

load_dotenv()  

class PresenceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

        self.logger = JiromiLogger()

        self.stats_buffer = {
            "chat_xp_events": 0,
            "voice_xp_events": 0,
            "voice_minutes": 0,
            "cmd_usage": 0
        }

    async def setup_hook(self):
        self.db = await init_db()
        self.logger.info("SYSTEM", "Database initialized (Shared Connection).")

        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and filename != "__init__.py":
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    self.logger.info("COG_LOAD", f"Loaded: {filename}")
                except Exception as e:
                    self.logger.error("COG_FAIL", f"Failed: {filename}", e)

        await self.tree.sync()
        self.logger.info("SYSTEM", "Slash commands synced.")

    async def close(self):
        # close_db dipanggil manual di blok finally main() agar urutan backup aman
        await super().close()

    async def on_ready(self):
        self.logger.info("BOT_READY", f"Logged in as: {self.user.name} ({self.user.id})")
        self.logger.info("BOT_READY", f"Connected to {len(self.guilds)} guilds.")

    async def on_guild_join(self, guild):
        self.logger.audit(
            "GUILD_JOIN",
            f"Joined: {guild.name} ({guild.id})",
            members=guild.member_count,
            owner_id=guild.owner_id
        )

    async def on_guild_remove(self, guild):
        self.logger.audit("GUILD_LEAVE", f"Left: {guild.name} ({guild.id})")

    async def on_resumed(self):
        # [FIX SENIOR] Deteksi Reconnect
        self.logger.audit("GATEWAY", "🔄 Session Resumed (Connection unstable but recovered)")

# --- LOGIKA SHUTDOWN HANDLING (Sesuai Arahan ) ---

async def perform_graceful_shutdown(bot):
    print("\n🛑 Shutdown Signal Received (Ctrl+C). Preparing Cleanup...")
    
    # 1. Hentikan Aktivitas Background (Agar DB Idle)
    # Kita unload cogs yang punya loop berat
    cogs_to_stop = ["Leveling", "WeeklyStats", "Monitor"]
    print("🧹 Stopping background loops...")
    
    for cog_name in cogs_to_stop:
        if bot.get_cog(cog_name):
            try:
                # Unload akan memicu method cog_unload() yang mematikan loop
                await bot.unload_extension(f"cogs.{cog_name.lower() if cog_name != 'WeeklyStats' else 'weekly_stats'}")
            except Exception as e:
                print(f"⚠️ Gagal stop {cog_name}: {e}")
    
    # Beri jeda 1 detik agar task benar-benar berhenti menulis
    await asyncio.sleep(1)

    # 2. JALANKAN BACKUP (Target Utama)
    print("💾 Running FINAL Database Backup...")
    backup_cog = bot.get_cog("OwnerBackup") # Pastikan class name di cogs/owner_backup.py adalah 'OwnerBackup'
    
    # ...
    if backup_cog:
        try:
            # PASTIKAN INI CUMA 2 VARIABLE, BUKAN 3
            zip_path, meta = await backup_cog.perform_backup_logic()
            
            if zip_path:
                print(f"✅ SHUTDOWN BACKUP SUCCESS: {zip_path}")
                print(f"📊 Stats: {meta['size_kb']}KB | {meta['users']} Users")
            else:
                print(f"❌ SHUTDOWN BACKUP FAILED: {meta}")
    # ...
        except Exception as e:
             print(f"❌ Error saat backup shutdown: {e}")
    else:
        print("⚠️ OwnerBackup Cog tidak ditemukan, skip backup.")

async def main():
    token = os.getenv("DISCORD_TOKEN")  
    if not token:
        raise RuntimeError("DISCORD_TOKEN tidak ditemukan di .env")

    bot = PresenceBot()

    try:
        # Jalankan bot dalam blok async context manager
        async with bot:
            await bot.start(token)
            
    except KeyboardInterrupt:
        # INI ADALAH "GOLDEN WINDOW" SAAT KAMU TEKAN CTRL+C
        # Python akan masuk ke sini sebelum mematikan program sepenuhnya.
        await perform_graceful_shutdown(bot)
        
    finally:
        # Apapun yang terjadi (Error atau Ctrl+C), tutup DB dengan benar
        print("👋 Closing Database connection...")
        await close_db()
        print("✅ System Offline.")

if __name__ == "__main__":
    try:
        # Gunakan asyncio.run() yang standar
        asyncio.run(main())
    except KeyboardInterrupt:
        # Catch terakhir jika exception bocor keluar dari main()
        pass