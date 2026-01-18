# main.py
import discord
from discord.ext import commands
import os
import asyncio
from utils.db_handler import init_db, DatabaseHandler

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
        
        # Inisialisasi handler database 
        self.db = DatabaseHandler()

    async def setup_hook(self):
        """Dijalankan saat bot pertama kali menyala untuk menyiapkan infrastruktur."""
        
        await init_db()
        print("Database initialized.")

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and filename != "__init__.py":
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Loaded Cog: {filename}")
                except Exception as e:
                    print(f"❌ Failed to load Cog {filename}: {e}")

        await self.tree.sync()
        print("Slash commands synced.")

    async def on_ready(self):
        print(f"---")
        print(f"Logged in as: {self.user.name} (ID: {self.user.id})")
        print(f"Jiromi is ready to honor community participation.")
        print(f"---")

# Inisialisasi dan jalankan bot
async def main():
    bot = PresenceBot()
    async with bot:
        await bot.start("MTQ1ODc1MzUzMDM4MTcyOTkyOA.GWW9_z.ksInEOW_rPspKmHAshZ2t3GCU4-RQu76mrEXHg")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot offline.")
