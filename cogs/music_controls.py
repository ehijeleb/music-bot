import discord
from discord.ui import Button, View

class MusicControlView(View):
    def __init__(self, bot, ctx, voice_client):
        super().__init__()
        self.bot = bot
        self.ctx = ctx
        self.voice_client = voice_client  # Store the voice client to access its state

        # Initialize buttons with correct enabled/disabled state
        self.pause_button.disabled = not self.voice_client.is_playing()  # Disable pause if not playing
        self.resume_button.disabled = not self.voice_client.is_paused()  # Disable resume if not paused

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.grey, emoji="⏸️")
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()

            # Disable the pause button and enable the resume button
            self.pause_button.disabled = True
            self.resume_button.disabled = False

            # Update the message with the new button states
            await interaction.response.edit_message(content="⏸️ Paused the song!", view=self)
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.green, emoji="▶️")
    async def resume_button(self, interaction: discord.Interaction, button: Button):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()

            # Disable the resume button and enable the pause button
            self.resume_button.disabled = True
            self.pause_button.disabled = False

            # Update the message with the new button states
            await interaction.response.edit_message(content="▶️ Resumed the song!", view=self)
        else:
            await interaction.response.send_message("No song is currently paused.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.red, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        voice_client = interaction.guild.voice_client
        if voice_client.is_playing():
            voice_client.stop()

            # Keep the pause and resume buttons disabled after skipping
            self.pause_button.disabled = True
            self.resume_button.disabled = True

            # Update the message with the new button states
            await interaction.response.edit_message(content="⏭️ Skipped the current song!", view=self)
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)
