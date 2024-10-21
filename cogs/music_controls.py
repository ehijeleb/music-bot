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
            # Acknowledge the interaction immediately to prevent "Interaction failed"
            await interaction.response.defer()

            voice_client.pause()

            # Disable the pause button and enable the resume button
            self.pause_button.disabled = True
            self.resume_button.disabled = False

            # Update the view with the new button states
            await interaction.message.edit(view=self)

            # Send a new message in the chat to notify users
            await interaction.channel.send(f"⏸️ {interaction.user.mention} paused the song!")
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.green, emoji="▶️")
    async def resume_button(self, interaction: discord.Interaction, button: Button):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            # Acknowledge the interaction immediately to prevent "Interaction failed"
            await interaction.response.defer()

            voice_client.resume()

            # Disable the resume button and enable the pause button
            self.resume_button.disabled = True
            self.pause_button.disabled = False

            # Update the view with the new button states
            await interaction.message.edit(view=self)

            # Send a new message in the chat to notify users
            await interaction.channel.send(f"▶️ {interaction.user.mention} resumed the song!")
        else:
            await interaction.response.send_message("No song is currently paused.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.red, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        voice_client = interaction.guild.voice_client
        if voice_client.is_playing():
            # Acknowledge the interaction immediately to prevent "Interaction failed"
            await interaction.response.defer()

            voice_client.stop()

            # Disable both buttons after skipping
            self.pause_button.disabled = True
            self.resume_button.disabled = True

            # Update the view with the new button states
            await interaction.message.edit(view=self)

            # Send a new message in the chat to notify users
            await interaction.channel.send(f"⏭️ {interaction.user.mention} skipped the song!")
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)
