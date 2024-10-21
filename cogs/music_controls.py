import discord
from discord.ui import Button, View

class MusicControlView(View):
    def __init__(self, bot, ctx):
        super().__init__()
        self.bot = bot
        self.ctx = ctx  # Storing ctx for other use cases if needed

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.grey, emoji="⏸️")
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        # Access the voice client from interaction.guild
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Paused the song!", ephemeral=True)
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.green, emoji="▶️")
    async def resume_button(self, interaction: discord.Interaction, button: Button):
        # Access the voice client from interaction.guild
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Resumed the song!", ephemeral=True)
        else:
            await interaction.response.send_message("No song is currently paused.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.red, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        # Access the voice client from interaction.guild
        voice_client = interaction.guild.voice_client
        if voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped the current song!", ephemeral=True)
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)
