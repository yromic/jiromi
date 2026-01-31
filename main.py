# main.py
import discord
from discord.ext import commands
import os
import asyncio
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
        await close_db()
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


async def main():
    token = os.getenv("DISCORD_TOKEN")  

    if not token:
        raise RuntimeError("DISCORD_TOKEN tidak ditemukan. Pastikan file .env sudah ada dan berisi DISCORD_TOKEN=...")

    bot = PresenceBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot offline.")
