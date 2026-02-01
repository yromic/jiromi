import discord
from discord.ext import commands, tasks
import asyncio
import math # Import math untuk cek infinity

class Monitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stat_loop.start()

    def cog_unload(self):
        # [POIN 5 Senior] Pastikan loop mati saat reload extension
        self.stat_loop.cancel()

    @tasks.loop(minutes=10)
    async def stat_loop(self):
        try:
            # 1. Guard Clause: Bot belum siap? Skip dulu
            if not self.bot.is_ready():
                return

            # 2. Ambil Latency dengan Aman (Bug Kelas 2 Fix)
            # Kita gabung logika seniormu + math check biar makin kuat
            lat = self.bot.latency
            latency_display = (
                f"{round(lat * 1000)}ms" 
                if lat is not None and not math.isinf(lat) 
                else "N/A"
            )

            # 3. Hitung Guild & Member dengan Aman (Bug Kelas 3 Fix)
            # Menggunakan 'or 0' untuk handle jika member_count None saat reconnect
            guild_count = len(self.bot.guilds)
            user_count = sum(g.member_count or 0 for g in self.bot.guilds)

            # 4. Siapkan Data Statistik
            stats = {
                "guilds": guild_count,
                "users": user_count,
                "latency": latency_display,
                # Ambil langsung dari buffer bot
                "chat_ev": self.bot.stats_buffer.get("chat_xp_events", 0),
                "voice_ev": self.bot.stats_buffer.get("voice_xp_events", 0),
                "voice_mins": self.bot.stats_buffer.get("voice_minutes", 0),
            }

            # 5. Log ke Console/File (Memory Only, No DB Access)
            self.bot.logger.stat(stats)

            # 6. Reset Buffer (Langsung di sini biar atomik)
            self.bot.stats_buffer.update({
                "chat_xp_events": 0,
                "voice_xp_events": 0,
                "voice_minutes": 0,
                "cmd_usage": 0
            })

        except Exception as e:
            # Bug Kelas 1 Fix: Catch-All di dalam body loop
            self.bot.logger.error("MONITOR_LOOP", "Unhandled error in stats loop", error_obj=e)

    @stat_loop.before_loop
    async def before_stats(self):
        await self.bot.wait_until_ready()

    # [FIX UTAMA] Bug Kelas 5: Auto-Restart saat Crash Fatal
    @stat_loop.error
    async def stat_loop_error(self, error):
        if self.bot.is_shutting_down:
            return 
        
        self.bot.logger.error(
            "MONITOR_CRASH", 
            "Monitor loop mati mendadak! Mencoba restart dalam 5 detik...", 
            error_obj=error
        )
        # Tunggu sebentar biar gak spam error kalau masalahnya persisten
        await asyncio.sleep(5)
        
        # Hidupkan kembali loop-nya
        self.stat_loop.restart()

async def setup(bot):
    await bot.add_cog(Monitor(bot))