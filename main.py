import discord
from discord.ext import commands
import os
import asyncio
import sys 
from dotenv import load_dotenv  
from utils.db_handler import init_db, close_db
from utils.logger import JiromiLogger
import signal

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

        self.is_shutting_down = False

        self.shutdown_complete = asyncio.Event()

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

        self.logger.audit("GATEWAY", "[RESUME] Session Resumed (Connection unstable but recovered)")


async def perform_graceful_shutdown(bot):
    if bot.is_shutting_down: return
    bot.is_shutting_down = True
    
    print("\n[SHUTDOWN] Shutdown Signal Received. Preparing Cleanup...")
    
    cogs_to_stop = ["Leveling", "WeeklyStats", "Monitor"]
    print("[SHUTDOWN] Stopping background loops...")
    
    for cog_name in cogs_to_stop:
        if bot.get_cog(cog_name):
            try:

                await bot.unload_extension(f"cogs.{cog_name.lower() if cog_name != 'WeeklyStats' else 'weekly_stats'}")
            except Exception as e:
                print(f"[WARN] Gagal stop {cog_name}: {e}")
    
    await asyncio.sleep(1)

    print("[BACKUP] Running FINAL Database Backup...")
    backup_cog = bot.get_cog("OwnerBackup") 
    
    
    if backup_cog:
        try:
            zip_path, meta = await backup_cog.perform_backup_logic()
            if zip_path:
                print(f"[SUCCESS] SHUTDOWN BACKUP SUCCESS: {zip_path}")
            else:
                print(f"[FAIL] SHUTDOWN BACKUP FAILED: {meta}")
        except Exception as e:
             print(f"[FAIL] Error saat backup shutdown: {e}")
    
    print("[SHUTDOWN] Disconnecting from Gateway...")
    await bot.close()

    print("[SHUTDOWN] Closing Database connection...")
    await close_db()

    bot.shutdown_complete.set()

def register_signals(bot):
    loop = asyncio.get_running_loop()

    def signal_handler():

        if bot.is_shutting_down:
            return 
        asyncio.create_task(perform_graceful_shutdown(bot))

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:

            pass

async def main():
    token = os.getenv("DISCORD_TOKEN")  
    if not token:
        raise RuntimeError("DISCORD_TOKEN tidak ditemukan di .env")

    bot = PresenceBot()

    try:
        await bot.login(token)
        register_signals(bot)
        
        try:
            await bot.connect()
        except asyncio.CancelledError:
            pass
            
    except Exception as e:
        print(f"[FATAL ERROR] FATAL STARTUP ERROR: {e}")
        
    finally:

        if bot.is_shutting_down:
            print("[WAIT] Menunggu proses shutdown selesai...")
            await bot.shutdown_complete.wait()

        else:
            print("[WARN] Shutdown tak terduga (Crash). Memulai cleanup darurat...")
            await perform_graceful_shutdown(bot)

if __name__ == "__main__":
    try:

        asyncio.run(main())
    except KeyboardInterrupt:

        pass