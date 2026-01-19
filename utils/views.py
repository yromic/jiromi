# FILE: utils/views.py
import discord
from discord import ui
from typing import Optional

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
            msg = "⛔ **Akses Ditolak.** Tombol ini hanya milik eksekutor command."
            
            # [FIX 4] Cek apakah interaksi sudah direspon sebelumnya (Edge Case)
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        # Disable semua tombol
        for child in self.children:
            child.disabled = True
        
        # [FIX 3] Error Handling yang tidak 'blind'
        if self.message:
            try:
                # [FIX 2] Jangan replace embed! Cukup update view & tambah konten teks kecil
                await self.message.edit(
                    content="⌛ **Waktu Habis.** Interaksi dinonaktifkan.", 
                    view=self
                )
            except (discord.NotFound, discord.Forbidden):
                # Pesan sudah dihapus atau bot tidak punya izin, abaikan.
                pass
            except Exception as e:
                # Idealnya log ke file, tapi print cukup untuk sekarang
                print(f"⚠️ Error pada View Timeout: {e}")