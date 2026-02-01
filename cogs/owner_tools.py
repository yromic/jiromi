import discord
from discord import app_commands
from discord.ext import commands

class OwnerTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="guilds",
        description="(Owner) List semua guild tempat bot bergabung"
    )
    async def list_guilds(self, interaction: discord.Interaction):
        # --- OWNER CHECK ---
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ Command ini hanya untuk owner bot.",
                ephemeral=True
            )
            return

        guilds = self.bot.guilds
        if not guilds:
            await interaction.response.send_message(
                "Bot tidak bergabung di guild manapun.",
                ephemeral=True
            )
            return

        lines = []
        for i, g in enumerate(guilds, start=1):
            is_owner = "yes" if g.owner_id == self.bot.user.id else "no"
            lines.append(
                f"**{i}. {g.name}**\n"
                f"• Guild ID: `{g.id}`\n"
                f"• Members: `{g.member_count}`\n"
                f"• Bot Owner: `{is_owner}`"
            )

        description = "\n\n".join(lines)

        embed = discord.Embed(
            title="📡 Jiromi – Guild Presence",
            description=description,
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Total guilds: {len(guilds)}")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(OwnerTools(bot))
