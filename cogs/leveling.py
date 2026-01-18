# cogs/leveling.py
import discord
from discord.ext import commands, tasks
import time

class Leveling(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.mute_tracker = {}
        self.failed_roles_cache = set()
        self.voice_heartbeat.start()

    def cog_unload(self):
        self.voice_heartbeat.cancel()

    @tasks.loop(minutes=1.0)
    async def voice_heartbeat(self):
        for guild in self.bot.guilds:
            config = await self.db.get_guild_config(guild.id)
            if not config:
                continue

            for vc in guild.voice_channels:
                active_members = [
                    m for m in vc.members
                    if not m.bot and not m.voice.self_deaf
                ]

                if len(active_members) < config['min_members_voice']:
                    continue

                for member in active_members:
                    if not await self.db.is_eligible(member, vc):
                        continue

                    await self.process_voice_xp(member, config)

    async def process_voice_xp(self, member, config):
        key = (member.guild.id, member.id)
        is_muted = member.voice.self_mute or member.voice.mute

        if is_muted:
            self.mute_tracker[key] = self.mute_tracker.get(key, 0) + 1
            if self.mute_tracker[key] > 5:
                return
        else:
            self.mute_tracker[key] = 0
            
        minutes = 1 
        xp_gain = minutes * config['voice_xp_val']

        result = await self.db.add_voice_time(
            member.id,
            member.guild.id,
            minutes, # Pakai variabel
            config['voice_xp_val']
        )
        
        # [HOOK] Update Weekly Stats
        await self.db.update_weekly_stats(
            guild_id=member.guild.id, 
            user_id=member.id, 
            xp_add=xp_gain, 
            voice_mins_add=minutes,
            chat_xp_add=0  # [PENTING] Chat XP nol karena ini voice
        )

        if result['new_level'] > result['old_level']:
            await self.handle_level_up(member, result['new_level'])

        self.bot.stats_buffer['voice_xp_events'] += 1
        self.bot.stats_buffer['voice_minutes'] += minutes
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        if not await self.db.is_eligible(message.author, message.channel):
            return

        user_data = await self.db.get_user_data(
            message.author.id,
            message.guild.id
        )

        if time.time() - user_data['last_chat_ts'] < 10:
            return

        if len(message.content) < 8:
            return

        config = await self.db.get_guild_config(message.guild.id)
        result = await self.db.add_chat_xp(
            message.author.id,
            message.guild.id,
            config['chat_xp_val']
        )
        
        # [HOOK] Update Weekly Stats
        await self.db.update_weekly_stats(
            guild_id=message.guild.id,
            user_id=message.author.id,
            xp_add=config['chat_xp_val'],
            voice_mins_add=0, # Voice nol karena ini chat
            chat_xp_add=config['chat_xp_val'] # [PENTING] Isi kolom chat
        )

        if result['new_level'] > result['old_level']:
            await self.handle_level_up(message.author, result['new_level'])
            
        self.bot.stats_buffer['chat_xp_events'] += 1

    # Di dalam cogs/leveling.py -> handle_level_up()

    async def handle_level_up(self, member, new_level):
        config = await self.db.get_guild_config(member.guild.id)
        mode = config['announcement_mode'] if config else 'balanced' 

        # 1. Cek Role Reward terlebih dahulu
        reward_role = await self.check_role_rewards(member, new_level) 

        # 2. Filter Logika Berdasarkan Mode
        if mode == "quiet":
            return # Tidak ada pengumuman sama sekali

        if mode == "balanced":
            # Hanya umumkan jika ada role baru [cite: 260-262]
            if reward_role:
                await self.handle_announcement(member, new_level, reward_role)
            return

        if mode == "loud":
            # Umumkan setiap naik level, baik ada role maupun tidak
            await self.handle_announcement(member, new_level, reward_role)
            
        rewards = await self.db.get_level_rewards(member.guild.id)
        
        for reward in rewards:
            if reward['level_required'] == new_level:
                role_id = reward['role_id']
                role = member.guild.get_role(role_id)
                
                if role:
                    try:
                        await member.add_roles(role, reason=f"Level Up to {new_level}")
                        # Log Sukses (Opsional, Info aja)
                        self.bot.logger.info("ROLE_GIVE", f"Gave role {role.name} to {member.name}", guild_id=member.guild.id)
                        
                    except discord.Forbidden:
                        # [FIX 5] Ganti print dengan Logger Error
                        self.bot.logger.error(
                            "ROLE_FORBIDDEN", 
                            f"Missing perms to give role {role.name}",
                            guild_id=member.guild.id,
                            user_id=member.id,
                            role_id=role.id
                        )
                    except Exception as e:
                        self.bot.logger.error(
                            "ROLE_FAIL", 
                            "Unknown error giving role",
                            e,
                            guild_id=member.guild.id
                        )

    async def check_role_rewards(self, member, level):
        rewards = await self.db.fetch_all(
            "SELECT level_required, role_id FROM rewards "
            "WHERE guild_id = ? ORDER BY level_required ASC",
            (member.guild.id,)
        )
        
        latest_role = None
        for row in rewards:
            if level >= row['level_required']:
                role_id = row['role_id']
                role = member.guild.get_role(role_id)
                
                # [BARU] Skip jika role tidak ada atau sudah ditandai gagal
                if not role: 
                    continue
                if (member.guild.id, member.id, role_id) in self.failed_roles_cache:
                    continue

                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Presence Reward")
                        latest_role = role
                        # Jika sukses, hapus dari cache kegagalan (kalau ada)
                        self.failed_roles_cache.discard((member.guild.id, member.id, role_id))
                        
                    except discord.Forbidden:
                        # [BARU] Tangkap error, masukkan ke cache, dan print warning SEKALI SAJA
                        self.failed_roles_cache.add((member.guild.id, member.id, role_id))
                        print(f" ⚠️  [Soft-Fail] Izin ditolak memberi role {role.name} di {member.guild.name}. Retry dihentikan untuk user ini.")
                    except Exception as e:
                        print(f" ❌  Error tak terduga saat memberi reward: {e}")

        return latest_role

    async def handle_announcement(self, member, level, new_role):
        config = await self.db.get_guild_config(member.guild.id)
        if not config or not config['announce_channel_id']:
            return

        channel = member.guild.get_channel(config['announce_channel_id'])
        if not channel:
            return
        
        # Cek Permission Bot di channel tersebut
        # (Penting agar tidak error jika bot tidak bisa kirim embed)
        perms = channel.permissions_for(member.guild.me)
        if not perms.send_messages:
            return

        # --- LOGIKA PESAN SPESIAL ---
        
        # KONDISI 1: DAPAT ROLE (Spesial / Mewah)
        # Ini akan jalan di mode 'Balanced' DAN 'Loud' saat user dapat role.
        if new_role:
            embed = discord.Embed(
                title="🏆 PENCAPAIAN BARU TERBUKA!",
                description=(
                    f"Selamat {member.mention}! Dedikasimu luar biasa.\n"
                    f"Kamu telah mencapai **Level {level}** dan mendapatkan gelar baru:\n\n"
                    f"# 🎖️ {new_role.mention}" 
                ),
                color=discord.Color.gold() # Warna Emas agar terasa premium
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Teruslah aktif untuk hadiah berikutnya!")
            
            try:
                # Kirim dengan mention user di luar embed agar notif masuk
                await channel.send(content=f"🎉 {member.mention}", embed=embed)
            except discord.Forbidden:
                # Fallback jika bot tidak punya izin embed
                await channel.send(f"🏆 Selamat {member.mention}! Kamu naik ke **Level {level}** dan mendapat role **{new_role.name}**!")

        # KONDISI 2: LEVEL UP BIASA (Standar)
        # Ini hanya jalan di mode 'Loud' saat user naik level tapi TIDAK dapat role.
        else:
            # Pesan teks simple agar tidak spam visual
            msg = f"🆙 **Level Up!** Selamat {member.mention}, kamu baru saja naik ke **Level {level}**."
            await channel.send(msg)

    @voice_heartbeat.before_loop
    async def before_voice_heartbeat(self):
        await self.bot.wait_until_ready()

# Ganti fungsi setup di bagian paling bawah cogs/leveling.py
async def setup(bot):
    # bot.db sudah diinisialisasi di main.py, jadi kita bisa langsung memakainya
    await bot.add_cog(Leveling(bot, bot.db))
