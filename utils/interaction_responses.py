"""Safe response helpers for Discord interactions."""


async def send_interaction_message(
    interaction,
    *,
    content=None,
    embed=None,
    ephemeral=True,
    view=None,
):
    """Send one interaction response, using a followup after acknowledgement."""
    response_target = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )
    return await response_target(
        content=content,
        embed=embed,
        ephemeral=ephemeral,
        view=view,
    )


async def send_interaction_error(interaction, message, *, ephemeral=True):
    """Send a plain-language error without exposing implementation details."""
    return await send_interaction_message(
        interaction,
        content=message,
        ephemeral=ephemeral,
    )
