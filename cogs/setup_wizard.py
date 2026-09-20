#cogs/setup_wizard
import discord
from discord import app_commands, ui
from discord.ext import commands
from dataclasses import dataclass

# --- 1. DATA CLASS (DRAFT CONFIG) ---
@dataclass
class SetupDraft:
    guild_id: int
    author_id: int
    # [FIX 1] Gunakan Type Hint yang benar
    announce_channel_id: int | None = None
    chat_xp_val: int = 5
    voice_xp_val: int = 10
    min_members_voice: int = 2
    announcement_mode: str = "balanced" 

    def reset(self):
        """[FIX 3] Helper untuk membersihkan data saat Restart."""
        self.announce_channel_id = None
        self.chat_xp_val = 5
        self.voice_xp_val = 10
        self.min_members_voice = 2
        self.announcement_mode = "balanced"

# --- 2. VIEW CLASS (LOGIKA UI) ---
class SetupWizardView(ui.View):
    def __init__(self, bot, draft: SetupDraft, step: int = 0):
        super().__init__(timeout=180) 
        self.bot = bot
        self.draft = draft
        self.step = step
        # [FIX 4] Simpan referensi pesan untuk edit saat timeout
        self.message: discord.Message | None = None 
        
        # Variabel untuk menyimpan component object (agar parsing aman)
        self.mode_select = None
        self.chan_select = None
        self.announce_mode_select = None
        
        self.setup_ui_for_current_step()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.draft.author_id:
            await interaction.response.send_message("Sesi setup ini milik admin lain.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        """[FIX 4] Edit pesan saat timeout."""
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                embed = discord.Embed(description="Waktu setup habis. Jalankan `/setup` untuk memulai lagi.", color=discord.Color.red())
                await self.message.edit(embed=embed, view=self)
            except:
                pass

    def setup_ui_for_current_step(self):
        self.clear_items() 

        # --- STEP 0: START ---
        if self.step == 0:
            start_btn = ui.Button(label="Mulai Setup", style=discord.ButtonStyle.green, custom_id="start")
            start_btn.callback = self.cb_start
            self.add_item(start_btn)
            
            cancel_btn = ui.Button(label="Batal", style=discord.ButtonStyle.red, custom_id="cancel")
            cancel_btn.callback = self.cb_cancel
            self.add_item(cancel_btn)

        # --- STEP 1: PRESET MODE ---
        elif self.step == 1:
            # [FIX 2] Simpan ke self.mode_select agar bisa diakses di callback
            self.mode_select = ui.Select(placeholder="Pilih Gaya Server...", options=[
                discord.SelectOption(label="Basic", value="basic", description="Chat 5, voice 5 XP; tanpa notifikasi."),
                discord.SelectOption(label="Standard", value="standard", description="Chat 5, voice 10 XP; saat dapat role."),
                discord.SelectOption(label="Full", value="full", description="Chat 10, voice 15 XP; setiap naik level."),
            ])
            self.mode_select.callback = self.cb_step1_select
            self.add_item(self.mode_select)

            # Tombol Batal
            cancel_btn = ui.Button(label="Batal", style=discord.ButtonStyle.red, row=1)
            cancel_btn.callback = self.cb_cancel
            self.add_item(cancel_btn)

        # --- STEP 2: CHANNEL SELECTION ---
        elif self.step == 2:
            # [FIX 2] Simpan ke self.chan_select
            self.chan_select = ui.ChannelSelect(
                placeholder="Pilih Channel Pengumuman...",
                channel_types=[discord.ChannelType.text],
                max_values=1
            )
            self.chan_select.callback = self.cb_step2_channel
            self.add_item(self.chan_select)

            skip_btn = ui.Button(label="Skip / Tanpa Channel", style=discord.ButtonStyle.secondary, row=1)
            skip_btn.callback = self.cb_step2_skip
            self.add_item(skip_btn)
            
            # [UPGRADE UX] Tombol Back
            back_btn = ui.Button(label="Kembali", style=discord.ButtonStyle.secondary, row=1)
            back_btn.callback = self.cb_back
            self.add_item(back_btn)

        # --- STEP 3: ANNOUNCEMENT MODE ---
        elif self.step == 3:
            options = [
                discord.SelectOption(label="Quiet (Hening)", value="quiet", description="Tidak ada pesan level up."),
                discord.SelectOption(label="Balanced (Seimbang)", value="balanced", description="Hanya pesan saat dapat Role Reward."),
                discord.SelectOption(label="Loud (Ramai)", value="loud", description="Pesan setiap naik level."),
            ]
            self.announce_mode_select = ui.Select(placeholder="Seberapa sering bot menyapa?", options=options)
            self.announce_mode_select.callback = self.cb_step3_select
            self.add_item(self.announce_mode_select)
            
            # [UPGRADE UX] Tombol Back
            back_btn = ui.Button(label="Kembali", style=discord.ButtonStyle.secondary, row=1)
            back_btn.callback = self.cb_back
            self.add_item(back_btn)

        # --- STEP 4: VOICE MIN MEMBERS ---
        elif self.step == 4:
            btn1 = ui.Button(label="1 Orang (Bebas)", style=discord.ButtonStyle.secondary, custom_id="v_1")
            btn1.callback = self.cb_step4_1
            self.add_item(btn1)

            btn2 = ui.Button(label="2 Orang (Anti-Farm)", style=discord.ButtonStyle.primary, custom_id="v_2")
            btn2.callback = self.cb_step4_2
            self.add_item(btn2)
            
            btn3 = ui.Button(label="3 Orang (Ketat)", style=discord.ButtonStyle.secondary, custom_id="v_3")
            btn3.callback = self.cb_step4_3
            self.add_item(btn3)

            # [UPGRADE UX] Tombol Back
            back_btn = ui.Button(label="Kembali", style=discord.ButtonStyle.secondary, row=1)
            back_btn.callback = self.cb_back
            self.add_item(back_btn)

        # --- STEP 5: SUMMARY & APPLY ---
        elif self.step == 5:
            apply_btn = ui.Button(label="Simpan pengaturan", style=discord.ButtonStyle.green)
            apply_btn.callback = self.cb_apply
            self.add_item(apply_btn)

            retry_btn = ui.Button(label="Ulangi dari Awal", style=discord.ButtonStyle.secondary)
            retry_btn.callback = self.cb_restart
            self.add_item(retry_btn)
            
            # [UPGRADE UX] Tombol Back
            back_btn = ui.Button(label="Kembali", style=discord.ButtonStyle.secondary)
            back_btn.callback = self.cb_back
            self.add_item(back_btn)

    # --- HELPERS ---

    async def update_view(self, interaction: discord.Interaction):
        self.setup_ui_for_current_step()
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self) -> discord.Embed:
        if self.step == 0:
            return discord.Embed(
                title="Setup Jiromi",
                description=(
                    "Wizard ini cocok untuk admin yang baru mengatur server.\n\n"
                    "Anda akan memilih preset XP chat dan voice, channel pengumuman, mode notifikasi, "
                    "dan jumlah minimum peserta voice agar XP berjalan."
                ),
                color=discord.Color.blue()
            )
        elif self.step == 1:
            return discord.Embed(title="1. Pilih preset", description="Nilai XP dan perilaku notifikasi setiap preset sudah dijelaskan pada pilihan di bawah.", color=discord.Color.blue())
        elif self.step == 2:
            return discord.Embed(title="2. Channel pengumuman", description="Pilih channel untuk pesan level up, atau lanjut tanpa pengumuman.", color=discord.Color.blue())
        elif self.step == 3:
            return discord.Embed(title="3. Mode notifikasi", description="Tentukan kapan bot mengirim pesan level up ke channel yang dipilih.", color=discord.Color.blue())
        elif self.step == 4:
            return discord.Embed(title="4. Aturan voice", description="Tentukan jumlah minimum peserta manusia di voice channel sebelum XP voice diberikan.", color=discord.Color.blue())
        elif self.step == 5:
            ch_text = f"<#{self.draft.announce_channel_id}>" if self.draft.announce_channel_id else "*(Tidak Ada)*"
            desc = (
                f"**Channel pengumuman:** {ch_text}\n"
                f"**Mode notifikasi:** `{self.draft.announcement_mode.upper()}`\n"
                f"**XP chat:** `{self.draft.chat_xp_val}` per pesan\n"
                f"**XP voice:** `{self.draft.voice_xp_val}` per menit\n"
                f"**Minimum peserta voice:** `{self.draft.min_members_voice} orang`\n\n"
                "Pilih Simpan pengaturan untuk menerapkan semua nilai ini."
            )
            return discord.Embed(title="5. Tinjau pengaturan", description=desc, color=discord.Color.gold())

    # --- CALLBACKS ---

    async def cb_start(self, interaction: discord.Interaction):
        self.step = 1
        await self.update_view(interaction)

    async def cb_cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Setup dibatalkan.", view=None, embed=None)
        self.stop()

    async def cb_back(self, interaction: discord.Interaction):
        """[UPGRADE UX] Logika tombol Back."""
        if self.step > 0:
            self.step -= 1
            # Special case: Kalau dari step 4 mundur ke 2 (karena tadi skip step 3)
            # Kita cek kondisi draft, tapi untuk simpelnya mundur 1 per 1 aja
            # Kalau user tadi skip channel, step 3 akan muncul, user bisa pilih mode lagi atau back lagi
            await self.update_view(interaction)

    async def cb_step1_select(self, interaction: discord.Interaction):
        # [FIX 2] Gunakan self.mode_select.values
        val = self.mode_select.values[0]
        
        if val == "basic":
            self.draft.chat_xp_val = 5
            self.draft.voice_xp_val = 5
            self.draft.announcement_mode = "quiet"
        elif val == "standard":
            self.draft.chat_xp_val = 5
            self.draft.voice_xp_val = 10
            self.draft.announcement_mode = "balanced"
        elif val == "full":
            self.draft.chat_xp_val = 10
            self.draft.voice_xp_val = 15
            self.draft.announcement_mode = "loud"
        
        self.step = 2
        await self.update_view(interaction)

    async def cb_step2_channel(self, interaction: discord.Interaction):
        # [FIX 2] Gunakan self.chan_select.values (Object Channel)
        # values return list of AppCommandChannel
        try:
            channel = self.chan_select.values[0]
            self.draft.announce_channel_id = channel.id
            self.step = 3
            await self.update_view(interaction)
        except IndexError:
            await interaction.response.send_message("⚠️ Mohon pilih channel.", ephemeral=True)

    async def cb_step2_skip(self, interaction: discord.Interaction):
        self.draft.announce_channel_id = None
        self.draft.announcement_mode = "quiet"
        self.step = 4 # Loncat langsung ke step 4
        await self.update_view(interaction)

    async def cb_step3_select(self, interaction: discord.Interaction):
        # [FIX 2] Gunakan object select
        val = self.announce_mode_select.values[0]
        self.draft.announcement_mode = val
        self.step = 4
        await self.update_view(interaction)

    async def cb_step4_1(self, interaction: discord.Interaction):
        self.draft.min_members_voice = 1
        self.step = 5
        await self.update_view(interaction)
    async def cb_step4_2(self, interaction: discord.Interaction):
        self.draft.min_members_voice = 2
        self.step = 5
        await self.update_view(interaction)
    async def cb_step4_3(self, interaction: discord.Interaction):
        self.draft.min_members_voice = 3
        self.step = 5
        await self.update_view(interaction)

    async def cb_restart(self, interaction: discord.Interaction):
        # [FIX 3] Reset draft value
        self.draft.reset()
        self.step = 0
        await self.update_view(interaction)

    async def cb_apply(self, interaction: discord.Interaction):
        await interaction.response.defer() # Defer biar gak timeout kalau DB lambat
        
        try:
            # 1. Update Config Dasar
            await self.bot.db.update_config(
                self.draft.guild_id,
                self.draft.announce_channel_id,
                self.draft.voice_xp_val,
                self.draft.chat_xp_val
            )
            # 2. Update Mode
            await self.bot.db.update_announcement_mode(
                self.draft.guild_id,
                self.draft.announcement_mode
            )
            # 3. Update Min Member
            await self.bot.db.update_min_members_voice(
                self.draft.guild_id,
                self.draft.min_members_voice
            )
            
            final_embed = discord.Embed(
                title="Setup selesai",
                description="Konfigurasi berhasil disimpan. Langkah berikutnya: `/xp status` lalu `/xp reward add` bila ingin menambah hadiah role.",
                color=discord.Color.green()
            )
            
            for child in self.children:
                child.disabled = True
                
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=final_embed, view=self)
            self.stop()
            
            self.bot.logger.audit(
            "SETUP_APPLY", 
            f"Setup applied for Guild: {interaction.guild.name}", # Tambah nama guild
            guild_id=interaction.guild_id,
            guild_name=interaction.guild.name, # Masuk ke JSONL
            actor_id=interaction.user.id,
            actor_name=interaction.user.name,  # Masuk ke JSONL (biar tau siapa pelakunya)
            mode=self.draft.announcement_mode
        )   
            
        except Exception as e:
            self.bot.logger.error("SETUP_APPLY_FAIL", "Setup wizard gagal menyimpan konfigurasi", error_obj=e, guild_id=self.draft.guild_id)
            self.setup_ui_for_current_step()
            failure_embed = self.get_embed()
            failure_embed.description = (
                "Pengaturan belum tersimpan sepenuhnya karena ada masalah saat menulis ke database. "
                "Draft Anda tetap ada. Pilih Simpan pengaturan untuk mencoba lagi, Kembali untuk mengubah nilai, atau Batal untuk keluar.\n\n"
                + (failure_embed.description or "")
            )
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=failure_embed, view=self)

# --- 3. COG CLASS ---
class SetupWizard(commands.Cog):
    # [FIX 5] Hapus parameter db yang redundant
    def __init__(self, bot, db=None): 
        self.bot = bot
        # Kita tidak simpan self.db disini karena akses via self.bot.db lebih aman jika db dipass di main

    @app_commands.command(name="setup", description="Wizard untuk admin baru: atur XP, pengumuman, dan batas voice langkah demi langkah.")
    @app_commands.checks.has_permissions(administrator=True)
    async def run_setup(self, interaction: discord.Interaction):
        draft = SetupDraft(
            guild_id=interaction.guild_id,
            author_id=interaction.user.id
        )
        
        view = SetupWizardView(self.bot, draft, step=0)
        
        await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)
        # [FIX 4] Simpan referensi pesan untuk timeout handling
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(SetupWizard(bot, bot.db))
