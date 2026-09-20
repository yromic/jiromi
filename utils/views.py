# FILE: utils/views.py
import discord
from discord import ui
from typing import Optional

from utils.interaction_responses import send_interaction_error


TIMEOUT_MESSAGE = "Waktu habis. Kontrol dinonaktifkan."

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
                if content:
                    content = f"{content}\n\n{TIMEOUT_MESSAGE}"
                else:
                    content = TIMEOUT_MESSAGE
                await self.message.edit(
                    content=content,
                    view=self
                )
            except (discord.NotFound, discord.Forbidden):
                # Pesan sudah dihapus atau bot tidak punya izin, abaikan.
                pass
            except Exception as e:
                # Idealnya log ke file, tapi print cukup untuk sekarang
                print(f"⚠️ Error pada View Timeout: {e}")
