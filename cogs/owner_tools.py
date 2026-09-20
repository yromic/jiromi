import discord
from discord import app_commands
from discord.ext import commands

from utils.interaction_responses import send_interaction_error, send_interaction_message


class OwnerTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="guilds", description="(Owner) Lihat daftar server yang diikuti bot.")
    async def list_guilds(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await send_interaction_error(interaction, "Perintah ini hanya dapat digunakan oleh owner bot.")
            return
        guilds = self.bot.guilds
        if not guilds:
            await send_interaction_message(interaction, content="Bot belum bergabung di server mana pun.")
            return
        lines = []
        for index, guild in enumerate(guilds, start=1):
            owner_status = "ya" if guild.owner_id == self.bot.user.id else "tidak"
            lines.append(f"**{index}. {guild.name}**\nID server: `{guild.id}`\nMember: `{guild.member_count}`\nOwner bot: `{owner_status}`")
        embed = discord.Embed(title="Server yang diikuti Jiromi", description="\n\n".join(lines), color=discord.Color.blurple())
        embed.set_footer(text=f"Total server: {len(guilds)}")
        await send_interaction_message(interaction, embed=embed)


async def setup(bot):
    await bot.add_cog(OwnerTools(bot))
