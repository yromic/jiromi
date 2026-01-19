#cogs/monitor
import discord
from discord.ext import commands, tasks

class Monitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stat_loop.start()

    def cog_unload(self):
        self.stat_loop.cancel()

    # Loop setiap 10 menit (Saran Senior)
    @tasks.loop(minutes=10)
    async def stat_loop(self):
        # Ambil data dari buffer bot
        buff = self.bot.stats_buffer
        
        # Siapkan data untuk Log Summary
        summary = {
            "guilds": len(self.bot.guilds),
            "users": sum([g.member_count for g in self.bot.guilds]),
            "latency": f"{round(self.bot.latency * 1000)}ms",
            "chat_ev": buff['chat_xp_events'],
            "voice_ev": buff['voice_xp_events'],
            "voice_mins": buff['voice_minutes']
        }
        
        # Print ke Console & File
        self.bot.logger.stat(summary)
        
        # Reset Buffer (Siap untuk 10 menit berikutnya)
        self.bot.stats_buffer['chat_xp_events'] = 0
        self.bot.stats_buffer['voice_xp_events'] = 0
        self.bot.stats_buffer['voice_minutes'] = 0
        self.bot.stats_buffer['cmd_usage'] = 0

    @stat_loop.before_loop
    async def before_stats(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Monitor(bot))