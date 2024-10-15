import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import logging
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# FFmpeg options
FFMPEG_BEFORE_OPTS = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
FFMPEG_OPTS = '-vn'  # Disable video, only get audio

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.allowed_channels = {} 

    def get_queue(self, guild):
        if guild.id not in self.queues:
            self.queues[guild.id] = []
        return self.queues[guild.id]

    async def check_channel(self, ctx):
        guild_id = ctx.guild.id
        if guild_id in self.allowed_channels:
            allowed_channel_id = self.allowed_channels[guild_id]
            if ctx.channel.id != allowed_channel_id:
                await ctx.send(f"Commands can only be used in <#{allowed_channel_id}>.")
                return False
        return True

    @commands.command(name="set")
    async def set(self, ctx):
        guild_id = ctx.guild.id
        self.allowed_channels[guild_id] = ctx.channel.id  
        await ctx.send(f"Commands can now only be used in this channel: {ctx.channel.mention}")
    
    @commands.command(name="join")
    async def join(self, ctx):
        if not await self.check_channel(ctx):  # Check if the command is allowed in this channel
            return

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
    async def play(self, ctx, *, query):
        if not await self.check_channel(ctx):
            return

        voice_client = ctx.guild.voice_client
        if not voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You need to be in a voice channel to play music.")
                return

        queue = self.get_queue(ctx.guild)
        # Add the song to the queue and start playing
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]',
            'noplaylist': True,
            'quiet': True,
        }

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                if "youtube.com" in query or "youtu.be" in query:
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]

                audio_url = info['url']
                title = info.get('title', 'Unknown Title')

            queue.append({
                'title': title,
                'url': audio_url,
                'requester': ctx.author,
            })
            await ctx.send(f"Added to queue: {title}")

            if not voice_client.is_playing():
                await self.play_next(ctx.guild)

        except Exception as e:
            logging.error(f"Error downloading video: {e}")
            await ctx.send("There was an error downloading your video or searching for the song.")

    async def play_next(self, guild):
        voice_client = guild.voice_client
        queue = self.get_queue(guild)

        if len(queue) > 0:
            song = queue.pop(0)
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(song['url'], before_options=FFMPEG_BEFORE_OPTS, options=FFMPEG_OPTS)
            )
            voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild)))

            # Send the message in the set allowed channel
            if guild.id in self.allowed_channels:
                allowed_channel_id = self.allowed_channels[guild.id]
                allowed_channel = self.bot.get_channel(allowed_channel_id)
                if allowed_channel:
                    await allowed_channel.send(f"Now playing: {song['title']} requested by {song['requester'].mention}")
        else:
            await voice_client.disconnect()

    @commands.command(name="queue")
    async def queue(self, ctx):
        if not await self.check_channel(ctx):
            return

        queue = self.get_queue(ctx.guild)

        if not queue:
            await ctx.send("The queue is currently empty.")
        else:
            queue_list = [f"{index + 1}. {song['title']} (requested by {song['requester'].mention})" for index, song in enumerate(queue)]
            message = "\n".join(queue_list)

            if len(message) > 2000:
                for chunk in [message[i:i + 2000] for i in range(0, len(message), 2000)]:
                    await ctx.send(chunk)
            else:
                await ctx.send(f"**Current Queue:**\n{message}")

    @commands.command(name="skip")
    async def skip(self, ctx):
        if not await self.check_channel(ctx):
            return

        voice_client = ctx.guild.voice_client
        if voice_client.is_playing():
            voice_client.stop()  
            await ctx.send("Skipped the current song.")
        else:
            await ctx.send("No song is currently playing.")

    

async def setup(bot):
    await bot.add_cog(Music(bot))