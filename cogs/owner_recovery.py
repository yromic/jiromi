#cogs/owner_recovery.py

import discord
from discord import app_commands
from discord.ext import commands
import asyncio

# --- KONFIGURASI SAFETY ---
MAX_XP_ACTION = 100000  # Batas maksimal XP sekali perintah (Anti Typo)

# Import dulu
from utils.views import ExecutorView 
from utils.interaction_responses import send_interaction_error

# Ganti class ConfirmView sepenuhnya:
# Di file: cogs/owner_recovery.py

class ConfirmView(ExecutorView):
    def __init__(self, author_id):
        super().__init__(author_id=author_id, timeout=30)
        self.value = None
        self._finished = False # [FIX 5] Anti Double Click

    @discord.ui.button(label="Jalankan", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
        
        # Kita tandai view selesai, tapi biarkan command di bawah memproses logic-nya
        # Kita cuma perlu matikan tombol dan kasih loading state
        await interaction.response.edit_message(view=self) 
        self.value = True
        self.stop()

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finished: return
        self._finished = True

        for child in self.children: child.disabled = True
        
        await interaction.response.edit_message(
            content="Dibatalkan. Tidak ada data yang diubah.",
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
                if role is None:
                    failed.append(f"ID {row['role_id']} (role tidak ditemukan)")
                    self.bot.logger.error(
                        "XP_GRANT_ROLE_MISSING",
                        "Role reward tidak ditemukan setelah perubahan XP tersimpan",
                        guild_id=guild.id,
                        member_id=member.id,
                        role_id=row['role_id'],
                    )
                elif role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Recovery: XP Grant")
                        added.append(role.name)
                    except discord.Forbidden:
                        failed.append(role.name)
                    except Exception as error:
                        failed.append(role.name)
                        self.bot.logger.error(
                            "XP_GRANT_ROLE_FAIL",
                            "Gagal memberikan role reward setelah perubahan XP tersimpan",
                            error_obj=error,
                            guild_id=guild.id,
                            member_id=member.id,
                            role_id=role.id,
                        )
        return added, failed

    # --- COMMAND 1: GRANT PER USER ---
    @app_commands.command(name="grant_user", description="Berikan XP ke satu user tertentu.")
    @app_commands.describe(member="Member target", amount="0 sampai 100.000 XP", mode="Add menambah XP; Set mengganti total XP")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Add (Menambahkan)", value="add"),
        app_commands.Choice(name="Set (Mengatur Ulang)", value="set")
    ])
    @app_commands.check(is_bot_owner)
    async def grant_user(self, interaction: discord.Interaction, member: discord.Member, amount: int, mode: app_commands.Choice[str]):
        # Safety Guard (Saran Senior No. 5)
        if amount < 0 or amount > MAX_XP_ACTION:
            return await interaction.response.send_message(f"Nilai harus dari 0 sampai {MAX_XP_ACTION:,} XP per aksi.", ephemeral=True)

        current = await self.db.fetch_one(
            "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
            (member.id, interaction.guild.id),
        )
        old_xp = current["xp"] if current else 0
        old_level = current["level"] if current else 0
        if mode.value == "add":
            action_text = (
                f"Tambah {amount:,} XP. Snapshot saat ini: {old_xp:,} XP; perkiraan total: {old_xp + amount:,} XP. "
                "Nilai final akan ditampilkan setelah disimpan."
            )
        else:
            action_text = f"Atur total XP menjadi {amount:,} XP. Snapshot saat ini: {old_xp:,} XP."
            if amount < old_xp:
                action_text += " Nilai yang lebih rendah dapat menurunkan level dan tidak mencabut role reward yang sudah ada."

        view = ConfirmView(author_id=interaction.user.id)
        embed = discord.Embed(
            title="Konfirmasi perubahan XP",
            description=f"Target: {member.mention}\nLevel saat ini: {old_level}\n\n{action_text}\n\nBatas per aksi: {MAX_XP_ACTION:,} XP.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
        await view.wait()

        if not view.value:
            return

        # Eksekusi
        old_xp, old_lvl, new_lvl, total_xp = await self.db.update_user_xp_direct(member.id, interaction.guild.id, amount, mode.value)
        
        # Apply Role
        roles_added, roles_failed = [], []
        if new_lvl > old_lvl:
            roles_added, roles_failed = await self._apply_roles_silent(interaction.guild, member, new_lvl)

        # Report
        partial = bool(roles_failed)
        res_embed = discord.Embed(
            title="XP tersimpan, tetapi role perlu diperiksa" if partial else "Perubahan XP tersimpan",
            color=discord.Color.orange() if partial else discord.Color.green(),
        )
        res_embed.add_field(name="Member", value=member.mention, inline=True)
        res_embed.add_field(name="Level", value=f"{old_lvl} → **{new_lvl}**", inline=True)
        res_embed.add_field(name="Total XP", value=f"{old_xp:,} → **{total_xp:,}**", inline=True)
        
        if roles_added:
            res_embed.add_field(name="Role (+)", value=", ".join(roles_added), inline=False)
        if roles_failed:
            res_embed.add_field(name="Role tidak diberikan", value=", ".join(roles_failed), inline=False)

        await interaction.followup.send(embed=res_embed, ephemeral=True)

    # --- COMMAND 2: MASS GRANT BY ROLE ---
    @app_commands.command(name="grant_mass", description="Berikan XP ke SEMUA user yang punya role tertentu.")
    @app_commands.check(is_bot_owner)
    async def grant_mass(self, interaction: discord.Interaction, role: discord.Role, amount: int):
        # Safety Guard
        if amount < 0 or amount > MAX_XP_ACTION:
            return await interaction.response.send_message(f"Nilai harus dari 0 sampai {MAX_XP_ACTION:,} XP per aksi.", ephemeral=True)

        members = [m for m in role.members if not m.bot] # Filter bot (Saran Senior No. 4)
        count = len(members)
        
        if count == 0:
            return await interaction.response.send_message("Role ini tidak memiliki member manusia.", ephemeral=True)

        view = ConfirmView(author_id=interaction.user.id)
        embed = discord.Embed(
            title="Konfirmasi perubahan XP massal",
            description=(
                f"Target: **{count} member** (Role: {role.mention})\n"
                f"Aksi: tambah **{amount:,} XP** untuk setiap member\n"
                f"Batas per aksi: {MAX_XP_ACTION:,} XP\n\n"
                "Progres akan diperbarui selama proses berlangsung."
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
        await view.wait()

        if not view.value:
            return

        # Status Awal
        status_msg = await interaction.followup.send(f"Memulai proses: 0/{count} member...", ephemeral=True)
        
        processed = 0
        failed_members = 0
        leveled_up = 0
        total_failed_roles = 0
        
        for member in members:
            try:
                _, old_lvl, new_lvl, _ = await self.db.update_user_xp_direct(member.id, interaction.guild.id, amount, "add")
                if new_lvl > old_lvl:
                    leveled_up += 1
                    _, failed = await self._apply_roles_silent(interaction.guild, member, new_lvl)
                    if failed:
                        total_failed_roles += 1
            except Exception as error:
                failed_members += 1
                self.bot.logger.error(
                    "MASS_XP_GRANT_MEMBER_FAIL",
                    "Gagal mengubah XP member pada grant massal",
                    error_obj=error,
                    guild_id=interaction.guild.id,
                    member_id=member.id,
                )
            processed += 1
            
            # Update Progress Bar (Saran Senior No. 1)
            # Update setiap 50 user agar tidak spam API tapi user tau bot jalan
            if processed % 50 == 0 or processed == count:
                try:
                    await status_msg.edit(content=f"Sedang memproses: {processed}/{count} member ({(processed/count)*100:.0f}%)")
                    await asyncio.sleep(1) # Pacing (Saran Senior)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
                    self.bot.logger.error(
                        "MASS_XP_PROGRESS_UPDATE_FAIL",
                        "Tidak dapat memperbarui progres grant massal; pemrosesan tetap berjalan",
                        error_obj=error,
                        guild_id=interaction.guild.id,
                        processed=processed,
                    )

        # Final Report
        partial = failed_members > 0 or total_failed_roles > 0
        final_embed = discord.Embed(
            title="Perubahan XP massal selesai dengan kendala" if partial else "Perubahan XP massal selesai",
            description=f"Target Role: {role.mention}",
            color=discord.Color.orange() if partial else discord.Color.green()
        )
        final_embed.add_field(name="Berhasil", value=str(processed - failed_members), inline=True)
        final_embed.add_field(name="Gagal", value=str(failed_members), inline=True)
        final_embed.add_field(name="Naik level", value=str(leveled_up), inline=True)
        
        if total_failed_roles > 0:
            final_embed.add_field(name="Role yang perlu diperiksa", value=f"{total_failed_roles} member belum mendapat role karena izin atau posisi role.", inline=False)
        
        # Edit pesan status terakhir menjadi laporan akhir.
        try:
            await status_msg.edit(content=None, embed=final_embed)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
            self.bot.logger.error("MASS_XP_FINAL_REPORT_EDIT_FAIL", "Tidak dapat mengganti pesan progres dengan hasil akhir", error_obj=error, guild_id=interaction.guild.id)
            await interaction.followup.send(embed=final_embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await send_interaction_error(interaction, "Fitur ini hanya dapat digunakan oleh owner bot.")
        else:
            self.bot.logger.error("OWNER_XP_COMMAND_FAIL", "Perintah pemulihan XP gagal", error_obj=error, guild_id=interaction.guild_id)
            await send_interaction_error(interaction, "Perubahan XP tidak dapat diproses. Coba lagi; periksa log jika masalah berulang.")

async def setup(bot):
    await bot.add_cog(OwnerRecovery(bot, bot.db))
