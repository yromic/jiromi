import asyncio
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.interaction_responses import send_interaction_error, send_interaction_message
from utils.views import ExecutorView


class WeeklyConfigConfirmView(ExecutorView):
    def __init__(self, cog, author_id, channel, enable):
        super().__init__(author_id=author_id, timeout=60)
        self.cog, self.channel, self.enable = cog, channel, enable

    @discord.ui.button(label="Konfirmasi", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction, button):
        self.stop()
        if self.enable:
            await self.cog.db.set_weekly_config(
                interaction.guild_id,
                recap_channel_id=self.channel.id,
                is_enabled=1,
                # A newly enabled recap starts with the next completed week.
                last_posted_week_key=self.cog.db.get_current_week_key(),
            )
            text = f"Rekap mingguan diaktifkan. Rekap akan dikirim ke {self.channel.mention} setelah minggu UTC berikutnya dimulai."
        else:
            await self.cog.db.set_weekly_config(interaction.guild_id, is_enabled=0)
            text = "Rekap mingguan dinonaktifkan. Channel yang sudah dipilih tetap tersimpan."
        await interaction.response.edit_message(content=text, view=None)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content="Perubahan rekap mingguan dibatalkan.", view=None)


class WeeklyStats(commands.Cog):
    def __init__(self, bot, db):
        self.bot, self.db = bot, db

    async def cog_load(self):
        self.weekly_recap_loop.start()

    def cog_unload(self):
        self.weekly_recap_loop.cancel()

    @staticmethod
    def _next_recap_time(now=None):
        now = now or datetime.now(timezone.utc)
        days = (7 - now.weekday()) % 7
        result = (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        return result + timedelta(days=7) if result <= now else result

    @app_commands.command(name="weekly_leaderboard", description="Aktivitas member dan server selama minggu UTC ini.")
    async def weekly_lb(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(thinking=True)
        except discord.InteractionResponded:
            pass
        except Exception as error:
            self.bot.logger.error("INTERACTION_FAIL", "Gagal menyiapkan leaderboard mingguan", error_obj=error)
            return
        started_at, guild = time.time(), interaction.guild
        if guild is None:
            await send_interaction_error(interaction, "Perintah ini hanya dapat digunakan di dalam server.")
            return
        week = self.db.get_current_week_key()
        totals = await self.db.fetch_one("""SELECT COALESCE(SUM(weekly_voice_mins),0) AS voice, COALESCE(SUM(weekly_chat_xp),0) AS chat, COALESCE(SUM(weekly_xp),0) AS xp FROM weekly_stats WHERE guild_id = ? AND week_key = ?""", (guild.id, week))
        rows = await self.db.fetch_all("""SELECT user_id, weekly_voice_mins, weekly_xp, weekly_chat_xp FROM weekly_stats WHERE guild_id = ? AND week_key = ? ORDER BY weekly_voice_mins DESC, weekly_xp DESC, user_id ASC LIMIT 10""", (guild.id, week))
        if not rows:
            await send_interaction_message(interaction, content="Belum ada aktivitas minggu ini. Coba lagi setelah member aktif di voice atau chat.")
            return
        rank, servers = await self.db.get_guild_weekly_rank(guild.id, week)
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"Voice: `{totals['voice']:,} menit` | Chat: `{totals['chat']:,} XP` | Total: `{totals['xp']:,} XP`", "", "**10 kontributor teratas**"]
        for position, row in enumerate(rows, 1):
            member = guild.get_member(row["user_id"])
            name = member.display_name if member else f"User-{row['user_id']}"
            prefix = medals[position - 1] if position <= 3 else f"#{position}"
            lines.append(f"{prefix} **{name}** — {row['weekly_voice_mins']} menit voice, {row['weekly_chat_xp']} XP chat, {row['weekly_xp']} XP total")
        if rank > 0:
            lines += ["", f"Server ini berada di peringkat #{rank} dari {servers} server aktif.", "Gunakan `/global leaderboard` untuk melihat peringkat anonim lintas server."]
        embed = discord.Embed(title=f"Leaderboard mingguan · {week}", description="\n".join(lines), color=discord.Color.gold())
        embed.set_footer(text="Statistik mingguan dimulai kembali setiap Senin (UTC).")
        self.bot.logger.info("BENCHMARK", f"Weekly Leaderboard selesai dalam {time.time() - started_at:.4f} detik")
        try:
            await interaction.followup.send(embed=embed)
        except (discord.NotFound, discord.HTTPException) as error:
            self.bot.logger.error("WEEKLY_CMD_FAIL", "Gagal mengirim leaderboard mingguan", error_obj=error)

    weekly_group = app_commands.Group(name="weekly", description="Atur pengiriman rekap aktivitas mingguan.")
    global_group = app_commands.Group(name="global", description="Lihat statistik anonim lintas server.")

    @global_group.command(name="leaderboard", description="10 server anonim dengan voice terbanyak minggu ini.")
    async def global_lb(self, interaction: discord.Interaction):
        await interaction.response.defer()
        week = self.db.get_current_week_key()
        rows = await self.db.fetch_all("""SELECT guild_id, SUM(weekly_voice_mins) AS total_voice FROM weekly_stats WHERE week_key = ? GROUP BY guild_id HAVING total_voice > 0 ORDER BY total_voice DESC LIMIT 10""", (week,))
        if not rows:
            await interaction.followup.send("Belum ada data global minggu ini.", ephemeral=True)
            return
        medals, lines = ["🥇", "🥈", "🥉"], []
        for position, row in enumerate(rows, 1):
            name = f"**Server ini ({interaction.guild.name})**" if row["guild_id"] == interaction.guild_id else f"Server #{row['guild_id'] % 1000:03d}"
            prefix = medals[position - 1] if position <= 3 else f"#{position}"
            lines.append(f"{prefix} {name} — `{row['total_voice']:,} menit voice`")
        embed = discord.Embed(title=f"Leaderboard global · {week}", description="10 server dengan voice terbanyak minggu ini:\n\n" + "\n".join(lines), color=discord.Color.blue())
        embed.set_footer(text="Nama server selain server ini disamarkan.")
        await interaction.followup.send(embed=embed)

    @weekly_group.command(name="enable", description="Pilih channel dan aktifkan rekap mingguan.")
    @app_commands.describe(channel="Channel tujuan rekap mingguan")
    @app_commands.checks.has_permissions(administrator=True)
    async def weekly_enable(self, interaction: discord.Interaction, channel: discord.TextChannel):
        view = WeeklyConfigConfirmView(self, interaction.user.id, channel, enable=True)
        await interaction.response.send_message(f"Aktifkan rekap mingguan ke {channel.mention}? Rekap dikirim setelah minggu UTC baru dimulai.", ephemeral=True, view=view)
        view.message = await interaction.original_response()

    @weekly_group.command(name="disable", description="Matikan pengiriman rekap; channel tetap tersimpan.")
    @app_commands.checks.has_permissions(administrator=True)
    async def weekly_disable(self, interaction: discord.Interaction):
        config = await self.db.get_weekly_config(interaction.guild_id)
        if not config or not config["is_enabled"]:
            await send_interaction_message(interaction, content="Rekap mingguan sudah tidak aktif.")
            return
        view = WeeklyConfigConfirmView(self, interaction.user.id, None, enable=False)
        await interaction.response.send_message("Matikan rekap mingguan? Channel yang sudah dipilih akan tetap tersimpan.", ephemeral=True, view=view)
        view.message = await interaction.original_response()

    @weekly_group.command(name="status", description="Lihat konfigurasi, jadwal, dan kesehatan rekap mingguan.")
    @app_commands.checks.has_permissions(administrator=True)
    async def weekly_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, week = interaction.guild, self.db.get_current_week_key()
        config = await self.db.get_weekly_config(guild.id)
        activity = await self.db.fetch_one("""SELECT COUNT(*) AS participants, COALESCE(SUM(weekly_voice_mins),0) AS minutes FROM weekly_stats WHERE guild_id = ? AND week_key = ?""", (guild.id, week))
        top_user = await self.db.fetch_one("""SELECT user_id, weekly_voice_mins, weekly_xp FROM weekly_stats WHERE guild_id = ? AND week_key = ? ORDER BY weekly_voice_mins DESC, weekly_xp DESC LIMIT 1""", (guild.id, week))
        delivery = await self.db.fetch_one("""SELECT status, posted_at, last_error FROM weekly_recap_deliveries WHERE guild_id = ? ORDER BY COALESCE(posted_at, claimed_at) DESC LIMIT 1""", (guild.id,))
        last_success = await self.db.fetch_one("""SELECT week_key, posted_at FROM weekly_recap_deliveries WHERE guild_id = ? AND status = 'posted' AND posted_at IS NOT NULL ORDER BY posted_at DESC LIMIT 1""", (guild.id,))
        enabled = bool(config and config["is_enabled"])
        channel = guild.get_channel(config["recap_channel_id"]) if config else None
        if enabled and channel:
            state, color, recovery, channel_text = "Aktif", discord.Color.green(), "Tidak ada tindakan yang diperlukan.", channel.mention
        elif enabled:
            state, color, recovery, channel_text = "Perlu perhatian", discord.Color.orange(), "Channel tidak tersedia. Jalankan `/weekly enable` dan pilih channel yang masih dapat diakses bot.", "Channel tersimpan sudah tidak tersedia"
        else:
            state, color, recovery, channel_text = "Tidak aktif", discord.Color.light_grey(), "Jalankan `/weekly enable` untuk mulai mengirim rekap.", channel.mention if channel else "Belum ada channel yang tersedia"
        if last_success:
            last = f"{discord.utils.format_dt(datetime.fromtimestamp(last_success['posted_at'], timezone.utc), style='R')} (minggu {last_success['week_key']})"
        elif delivery and delivery["status"] == "failed":
            recovery = "Pengiriman terakhir gagal. Periksa channel lalu jalankan `/weekly enable` untuk memilih ulang channel."
        elif delivery and delivery["status"] == "pending":
            recovery = "Tunggu pengecekan rekap berikutnya. Jika tetap tidak terkirim, periksa channel lalu jalankan `/weekly enable`."
        last = last if last_success else "Belum ada rekap yang berhasil dikirim"
        if delivery and delivery["status"] == "failed":
            latest_attempt = "Percobaan terbaru gagal. Periksa channel dan izinnya."
        elif delivery and delivery["status"] == "pending":
            latest_attempt = "Rekap sedang menunggu percobaan pengiriman."
        elif delivery and delivery["status"] == "empty":
            latest_attempt = "Tidak ada aktivitas pada periode rekap terakhir."
        else:
            latest_attempt = "Tidak ada kegagalan atau percobaan tertunda terbaru."
        if top_user:
            member = guild.get_member(top_user["user_id"])
            name = member.display_name if member else f"User-{top_user['user_id']}"
            preview = f"{activity['participants']} member, {activity['minutes']:,} menit voice. Teratas: {name}."
        else:
            preview = "Belum ada aktivitas minggu ini."
        next_check = self.weekly_recap_loop.next_iteration
        next_check_text = discord.utils.format_dt(next_check, style="R") if next_check else "menunggu loop dimulai"
        embed = discord.Embed(title="Status rekap mingguan", color=color)
        embed.add_field(name="Status", value=f"{state}\nChannel: {channel_text}", inline=False)
        embed.add_field(name="Jadwal", value=f"Rekap berikutnya: {discord.utils.format_dt(self._next_recap_time(), style='R')}\nPengecekan berikutnya: {next_check_text}", inline=False)
        embed.add_field(name="Pengiriman terakhir", value=last, inline=False)
        embed.add_field(name="Percobaan terbaru", value=latest_attempt, inline=False)
        embed.add_field(name="Aktivitas minggu ini", value=preview, inline=False)
        embed.add_field(name="Jika perlu bantuan", value=recovery, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tasks.loop(minutes=30)
    async def weekly_recap_loop(self):
        if not self.bot.is_ready(): return
        try:
            for config in await self.db.fetch_all("SELECT * FROM weekly_config WHERE is_enabled = 1"):
                try: await self._process_single_guild_recap(config, self.db.get_current_week_key())
                except Exception as error: self.bot.logger.error("WEEKLY_GUILD_FAIL", f"Gagal rekap untuk guild {config['guild_id']}", error_obj=error)
        except Exception as error:
            self.bot.logger.error("WEEKLY_FATAL", "Error di loop utama", error_obj=error)

    async def _process_single_guild_recap(self, config, current_week):
        guild_id, guild = config["guild_id"], self.bot.get_guild(config["guild_id"])
        checkpoint = config["last_posted_week_key"]
        if checkpoint and current_week <= checkpoint:
            return
        if not guild or not await self.db.claim_weekly_recap(guild_id, current_week): return
        channel = guild.get_channel(config["recap_channel_id"])
        if not channel:
            await self.db.execute("UPDATE weekly_config SET is_enabled = 0 WHERE guild_id = ?", (guild_id,))
            await self.db.finish_weekly_recap(guild_id, current_week, "failed", "recap channel unavailable")
            return
        previous_week = self.db.get_week_key_for_date(datetime.now(timezone.utc) - timedelta(days=7))
        rows = await self.db.fetch_all("""SELECT user_id, weekly_voice_mins, weekly_xp FROM weekly_stats WHERE guild_id = ? AND week_key = ? ORDER BY weekly_voice_mins DESC LIMIT 10""", (guild_id, previous_week))
        if not rows:
            await self.db.finish_weekly_recap(guild_id, current_week, "empty")
            return
        medals, lines, cache = ["🥇", "🥈", "🥉"], [], {}
        for position, row in enumerate(rows, 1):
            member = guild.get_member(row["user_id"]); name = member.display_name if member else f"User-{row['user_id']}"
            prefix = medals[position - 1] if position <= 3 else f"#{position}"
            lines.append(f"{prefix} **{name}** — {row['weekly_voice_mins']} menit voice, {row['weekly_xp']} XP")
            if row["weekly_voice_mins"] > 60: await self.db.unlock_badge(row["user_id"], guild_id, "badge_voice_order")
            if row["user_id"] not in cache:
                result = await self.db.fetch_one("""SELECT COUNT(DISTINCT week_key) AS weeks_count FROM weekly_stats WHERE user_id = ? AND guild_id = ? AND weekly_voice_mins >= 60""", (row["user_id"], guild_id))
                cache[row["user_id"]] = result["weeks_count"] if result else 0
            if cache[row["user_id"]] >= 4 and await self.db.unlock_badge(row["user_id"], guild_id, "badge_common_path"):
                await self.db.unlock_title(row["user_id"], guild_id, "title_fellow_path")
        rank, total = await self.db.get_guild_weekly_rank(guild_id, previous_week)
        if rank > 0: lines += ["", f"Peringkat server: #{rank} dari {total} server aktif."]
        embed = discord.Embed(title=f"Rekap mingguan · {previous_week}", description="Aktivitas terbaik minggu lalu:\n\n" + "\n".join(lines), color=discord.Color.fuchsia())
        embed.set_footer(text="Aktivitas untuk minggu baru sudah mulai dihitung.")
        try:
            await channel.send(embed=embed); await self.db.finish_weekly_recap(guild_id, current_week, "posted")
        except Exception as error:
            self.bot.logger.error("WEEKLY_SEND_FAIL", f"Gagal mengirim rekap ke {channel.id}", error_obj=error)
            await self.db.finish_weekly_recap(guild_id, current_week, "failed", str(error))

    @weekly_recap_loop.error
    async def weekly_recap_error(self, error):
        if self.bot.is_shutting_down: return
        self.bot.logger.error("WEEKLY_LOOP_CRASH", "Loop rekap mingguan berhenti", error_obj=error)
        await asyncio.sleep(10)
        if not self.bot.is_closed() and not self.weekly_recap_loop.is_running():
            try: self.weekly_recap_loop.start()
            except RuntimeError as restart_error: self.bot.logger.error("WEEKLY_RESTART_FAIL", "Gagal menjalankan kembali loop rekap", error_obj=restart_error)

    @weekly_recap_loop.before_loop
    async def before_recap(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(WeeklyStats(bot, bot.db))
