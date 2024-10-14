import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import logging

# FFmpeg options
FFMPEG_BEFORE_OPTS = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
FFMPEG_OPTS = '-vn'  # Disable video, only get audio

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {} 

    def get_queue(self, guild):
        """Get or create the music queue for the guild."""
        if guild.id not in self.queues:
            self.queues[guild.id] = []
        return self.queues[guild.id]

    @commands.command(name="join")
    async def join(self, ctx):
        """Join the user's voice channel."""
        if ctx.author.voice:  # Check if the user is in a voice channel
            channel = ctx.author.voice.channel  # Get the user's voice channel
            if ctx.voice_client is None:
                await channel.connect()  # Connect to the user's voice channel
                await ctx.send(f"Joined {channel}")
            else:
                await ctx.voice_client.move_to(channel) 
        else:
            await ctx.send("You are not in a voice channel.")

    @commands.command(name="play")
    async def play(self, ctx, *, url):
        """Play a song from a YouTube URL or search term."""
        voice_client = ctx.guild.voice_client
        if not voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You need to be in a voice channel to play music.")
                return

        # Use yt-dlp to extract the audio URL
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]',
            'noplaylist': True,
            'quiet': True,
        }

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info['url']
                title = info.get('title', 'Unknown Title')

            # Add the song to the queue
            queue = self.get_queue(ctx.guild)
            queue.append({
                'title': title,
                'url': audio_url,
                'requester': ctx.author,
            })
            await ctx.send(f"Added to queue: {title}")

            # If the bot isn't already playing, start playing
            if not voice_client.is_playing():
                await self.play_next(ctx.guild)

        except Exception as e:
            logging.error(f"Error downloading video: {e}")
            await ctx.send("There was an error downloading your video.")

    async def play_next(self, guild):
        """Play the next song in the queue, if any."""
        voice_client = guild.voice_client
        queue = self.get_queue(guild)

        if len(queue) > 0:
            # Get the next song
            song = queue.pop(0)
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(song['url'], before_options=FFMPEG_BEFORE_OPTS, options=FFMPEG_OPTS)
            )
            voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild)))
            channel = discord.utils.get(guild.text_channels, name="general")  # Replace "general" with your text channel
            await channel.send(f"Now playing: {song['title']} requested by {song['requester'].mention}")
        else:
            await voice_client.disconnect()

    @commands.command(name="skip")
    async def skip(self, ctx):
        """Skip the current song."""
        voice_client = ctx.guild.voice_client
        if voice_client.is_playing():
            voice_client.stop()  # This will trigger the next song to play
            await ctx.send("Skipped the current song.")
        else:
            await ctx.send("No song is currently playing.")

async def setup(bot):
    await bot.add_cog(Music(bot))
