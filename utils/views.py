# FILE: utils/views.py
import discord
from discord import ui
from typing import Optional

from utils.interaction_responses import send_interaction_error


TIMEOUT_MESSAGE = "Waktu habis. Kontrol dinonaktifkan."
MAX_MESSAGE_CONTENT = 2000

class ExecutorView(ui.View):
    """
    Base View dengan keamanan tingkat tinggi:
    1. Executor Lock (Hanya pembuat command yang bisa klik).
    2. Timeout handling yang aman (tidak overwrite embed).
    3. Error handling yang spesifik.
    """
    def __init__(self, author_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        # [FIX 1] Type hint Optional agar editor tidak protes
        self.message: Optional[discord.Message] = None 

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await send_interaction_error(
                interaction,
                "Akses ditolak. Tombol ini hanya dapat digunakan oleh pembuat perintah.",
            )
            return False
        return True

    async def on_timeout(self):
        # Disable semua tombol
        for child in self.children:
            child.disabled = True
        
        # [FIX 3] Error Handling yang tidak 'blind'
        if self.message:
            try:
                content = self.message.content
                timeout_content = (
                    f"{content}\n\n{TIMEOUT_MESSAGE}"
                    if content
                    else TIMEOUT_MESSAGE
                )

                if len(timeout_content) <= MAX_MESSAGE_CONTENT:
                    await self.message.edit(content=timeout_content, view=self)
                else:
                    if len(self.children) < 25:
                        self.add_item(
                            ui.Button(
                                label="Waktu habis",
                                style=discord.ButtonStyle.secondary,
                                disabled=True,
                            )
                        )
                    else:
                        for child in self.children:
                            if isinstance(child, ui.Button):
                                child.label = "Waktu habis"
                                break
                            if isinstance(child, ui.Select):
                                child.placeholder = "Waktu habis"
                                break
                    await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden):
                # Pesan sudah dihapus atau bot tidak punya izin, abaikan.
                pass
            except Exception as e:
                client = self.message._state._get_client()
                logger = getattr(client, "logger", None)
                if logger:
                    logger.error(
                        "VIEW_TIMEOUT_EDIT_FAIL",
                        "Gagal memperbarui kontrol view yang kedaluwarsa",
                        error_obj=e,
                    )
