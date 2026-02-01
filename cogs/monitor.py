import discord
from discord.ext import commands, tasks
import math # Import math untuk cek infinity

class Monitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stat_loop.start()

    def cog_unload(self):
        # [POIN 5 Senior] Pastikan loop mati saat reload extension
        self.stat_loop.cancel()

    # [POIN 4 Helper] Fungsi reset buffer yang rapi
    def _reset_stats_buffer(self):
        self.bot.stats_buffer.update({
            "chat_xp_events": 0,
            "voice_xp_events": 0,
            "voice_minutes": 0,
            "cmd_usage": 0
        })

    # [POIN 3 Senior] Loop setiap 10 menit
    @tasks.loop(minutes=10)
    async def stat_loop(self):
        # [POIN 2 Senior] Guard Clause: Jangan jalan kalau bot belum siap
        if not self.bot.is_ready():
            return

        try:
            # Ambil data dari buffer bot
            buff = self.bot.stats_buffer
            
            # [POIN 1 Senior] Fix Latency Infinite Crash
            lat = self.bot.latency
            if lat is None or math.isinf(lat):
                latency_display = "N/A"
            else:
                latency_display = f"{round(lat * 1000)}ms"

            # [POIN 6 Senior] Defensive Code: Hitung user/guild dengan aman
            try:
                guild_count = len(self.bot.guilds)
                user_count = sum([g.member_count for g in self.bot.guilds])
            except Exception:
                guild_count = 0
                user_count = 0

            # Siapkan data untuk Log Summary
            summary = {
                "guilds": guild_count,
                "users": user_count,
                "latency": latency_display,
                "chat_ev": buff.get('chat_xp_events', 0),
                "voice_ev": buff.get('voice_xp_events', 0),
                "voice_mins": buff.get('voice_minutes', 0)
            }
            
            # Print ke Console & File
            self.bot.logger.stat(summary)
            
            # [POIN 4 Real Fix] Reset Buffer SETELAH log berhasil dicatat
            self._reset_stats_buffer()

        except Exception as e:
            # [POIN 3 Senior] Catch-All: Biar loop TIDAK MATI kalau ada error lain
            # Log errornya tapi jangan raise exception yang mematikan task
            self.bot.logger.error("MONITOR_LOOP", "Terjadi error pada loop monitor", error_obj=e)

    # Memastikan loop menunggu bot ready sebelum start pertama kali
    @stat_loop.before_loop
    async def before_stats(self):
        await self.bot.wait_until_ready()

    # [FIX FINAL] Global Task Error Handler
    @stat_loop.error
    async def stat_loop_error(self, error):
        self.bot.logger.error(
            "MONITOR_LOOP_CRASH", 
            "Monitor loop berhenti total (Critical)", 
            error_obj=error
        )
        # Opsional: Restart loop jika error bukan karena shutdown
        # self.stat_loop.restart()

async def setup(bot):
    await bot.add_cog(Monitor(bot))