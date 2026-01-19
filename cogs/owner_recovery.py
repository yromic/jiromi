#cogs/owner_recovery.py

import discord
from discord import app_commands
from discord.ext import commands
import asyncio

# --- KONFIGURASI SAFETY ---
MAX_XP_ACTION = 100000  # Batas maksimal XP sekali perintah (Anti Typo)

# Import dulu
from utils.views import ExecutorView 

# Ganti class ConfirmView sepenuhnya:
# Di file: cogs/owner_recovery.py

class ConfirmView(ExecutorView):
    def __init__(self, author_id):
        super().__init__(author_id=author_id, timeout=30)
        self.value = None
        self._finished = False # [FIX 5] Anti Double Click

    @discord.ui.button(label="YA, EKSEKUSI", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
        
        # Kita tandai view selesai, tapi biarkan command di bawah memproses logic-nya
        # Kita cuma perlu matikan tombol dan kasih loading state
        await interaction.response.edit_message(view=self) 
        self.value = True
        self.stop()

    @discord.ui.button(label="BATAL", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
        
        await interaction.response.edit_message(
            content="❌ **Dibatalkan.**", 
            embed=None, 
            view=None
        )
        self.value = False
        self.stop()

class OwnerRecovery(commands.GroupCog, name="recovery"):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    @staticmethod
    async def is_bot_owner(interaction: discord.Interaction) -> bool:
        return await interaction.client.is_owner(interaction.user)

    # --- HELPER: SILENT ROLE REWARD (IMPROVED) ---
    async def _apply_roles_silent(self, guild, member, level):
        """
        Cek dan berikan role reward.
        Return: (list_sukses, list_gagal)
        """
        rewards = await self.db.fetch_all(
            "SELECT level_required, role_id FROM rewards WHERE guild_id = ? ORDER BY level_required ASC",
            (guild.id,)
        )
        
        added = []
        failed = [] # Tracking failure (Saran Senior No. 3)

        for row in rewards:
            if level >= row['level_required']:
                role = guild.get_role(row['role_id'])
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Recovery: XP Grant")
                        added.append(role.name)
                    except discord.Forbidden:
                        failed.append(role.name)
                    except Exception:
                        pass 
        return added, failed

    # --- COMMAND 1: GRANT PER USER ---
    @app_commands.command(name="grant_user", description="Berikan XP ke satu user tertentu.")
    @app_commands.describe(member="Target User", amount="Jumlah XP/Nilai XP", mode="Add (Tambah) atau Set (Atur)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Add (Menambahkan)", value="add"),
        app_commands.Choice(name="Set (Mengatur Ulang)", value="set")
    ])
    @app_commands.check(is_bot_owner)
    async def grant_user(self, interaction: discord.Interaction, member: discord.Member, amount: int, mode: app_commands.Choice[str]):
        # Safety Guard (Saran Senior No. 5)
        if amount > MAX_XP_ACTION:
            return await interaction.response.send_message(f"⛔ **Safety Limit:** Maksimal {MAX_XP_ACTION:,} XP per aksi.", ephemeral=True)

        view = ConfirmView(author_id=interaction.user.id)
        embed = discord.Embed(
            title="⚠️ Konfirmasi XP Grant",
            description=f"Target: {member.mention}\nAksi: **{mode.name} {amount:,} XP**",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
        await view.wait()

        if not view.value:
            return await interaction.followup.send("❌ Dibatalkan.", ephemeral=True)

        # Eksekusi
        old_lvl, new_lvl, total_xp = await self.db.update_user_xp_direct(member.id, interaction.guild.id, amount, mode.value)
        
        # Apply Role
        roles_added, roles_failed = [], []
        if new_lvl > old_lvl:
            roles_added, roles_failed = await self._apply_roles_silent(interaction.guild, member, new_lvl)

        # Report
        res_embed = discord.Embed(title="✅ Recovery Sukses", color=discord.Color.green())
        res_embed.add_field(name="User", value=member.mention, inline=True)
        res_embed.add_field(name="Level Update", value=f"{old_lvl} ➜ **{new_lvl}**", inline=True)
        
        if roles_added:
            res_embed.add_field(name="Role (+)", value=", ".join(roles_added), inline=False)
        if roles_failed:
            res_embed.add_field(name="Role Gagal (Izin Ditolak)", value=", ".join(roles_failed), inline=False)

        await interaction.followup.send(embed=res_embed, ephemeral=True)

    # --- COMMAND 2: MASS GRANT BY ROLE ---
    @app_commands.command(name="grant_mass", description="Berikan XP ke SEMUA user yang punya role tertentu.")
    @app_commands.check(is_bot_owner)
    async def grant_mass(self, interaction: discord.Interaction, role: discord.Role, amount: int):
        # Safety Guard
        if amount > MAX_XP_ACTION:
            return await interaction.response.send_message(f"⛔ **Safety Limit:** Maksimal {MAX_XP_ACTION:,} XP per aksi.", ephemeral=True)

        members = [m for m in role.members if not m.bot] # Filter bot (Saran Senior No. 4)
        count = len(members)
        
        if count == 0:
            return await interaction.response.send_message("❌ Role ini tidak memiliki member manusia.", ephemeral=True)

        view = ConfirmView(author_id=interaction.user.id)
        embed = discord.Embed(
            title="🚨 MASS XP RECOVERY",
            description=(
                f"Target: **{count} member** (Role: {role.mention})\n"
                f"Amount: **+{amount:,} XP** per user\n\n"
                "⚠️ Bot akan memproses secara bertahap."
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
        await view.wait()

        if not view.value:
            return await interaction.followup.send("❌ Dibatalkan.", ephemeral=True)

        # Status Awal
        status_msg = await interaction.followup.send(f"⏳ **Memulai Proses:** 0/{count} member...")
        
        processed = 0
        leveled_up = 0
        total_failed_roles = 0
        
        for member in members:
            # Update DB
            old_lvl, new_lvl, _ = await self.db.update_user_xp_direct(member.id, interaction.guild.id, amount, "add")
            
            if new_lvl > old_lvl:
                leveled_up += 1
                _, failed = await self._apply_roles_silent(interaction.guild, member, new_lvl)
                if failed: total_failed_roles += 1
            
            processed += 1
            
            # Update Progress Bar (Saran Senior No. 1)
            # Update setiap 50 user agar tidak spam API tapi user tau bot jalan
            if processed % 50 == 0:
                try:
                    await status_msg.edit(content=f"⏳ **Sedang Memproses:** {processed}/{count} member... ({(processed/count)*100:.0f}%)")
                    await asyncio.sleep(1) # Pacing (Saran Senior)
                except:
                    pass

        # Final Report
        final_embed = discord.Embed(
            title="✅ Mass Recovery Selesai",
            description=f"Target Role: {role.mention}",
            color=discord.Color.green()
        )
        final_embed.add_field(name="Total Member", value=str(processed), inline=True)
        final_embed.add_field(name="Naik Level", value=str(leveled_up), inline=True)
        
        if total_failed_roles > 0:
            final_embed.add_field(name="⚠️ Isu Permission", value=f"{total_failed_roles} user gagal dapat role (Cek Log)", inline=False)
        
        # Edit pesan status terakhir menjadi report akhir
        await status_msg.edit(content=None, embed=final_embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("⛔ Fitur ini khusus Owner Bot.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(OwnerRecovery(bot, bot.db))