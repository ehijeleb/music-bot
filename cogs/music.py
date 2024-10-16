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

    def get_queue(self, guild):
        if guild.id not in self.queues:
            self.queues[guild.id] = []
        return self.queues[guild.id]

    async def check_channel(self, ctx):
        guild_id = ctx.guild.id
        
        # Fetch the allowed channel from Supabase
        allowed_channel_id = await self.fetch_allowed_channel(guild_id)
        
        if allowed_channel_id is not None:
            # Ensure allowed_channel_id is cast to an integer for comparison
            allowed_channel_id = int(allowed_channel_id)
            
            if ctx.channel.id != allowed_channel_id:
                # If the current channel is not the allowed one, send a message
                await ctx.send(f"Commands can only be used in <#{allowed_channel_id}>.")
                return False
        
        # If no allowed channel is set or the command is in the allowed channel, return True
        return True

    
    async def fetch_allowed_channel(self, guild_id):
        response = supabase.table('channels').select('channel_id').eq('server_id', guild_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]['channel_id']
        return None

    async def set_allowed_channel(self, guild_id, channel_id):
        # Check if there is already an entry for this guild
        response = supabase.table('channels').select('server_id').eq('server_id', guild_id).execute()
        
        # Add logging to verify the current data in the table
        logging.info(f"Supabase select response for set_allowed_channel: {response.data}")
        
        if response.data and len(response.data) > 0:
            # Update the existing entry
            supabase.table('channels').update({'channel_id': channel_id}).eq('server_id', guild_id).execute()
            logging.info(f"Updated allowed channel for guild {guild_id} to channel {channel_id}")
        else:
            # Insert a new entry
            supabase.table('channels').insert({'server_id': guild_id, 'channel_id': channel_id}).execute()
            logging.info(f"Inserted new allowed channel for guild {guild_id} to channel {channel_id}")


    @commands.command(name="set")
    async def set(self, ctx):
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id
        
        # Store the allowed channel in the database
        await self.set_allowed_channel(guild_id, channel_id)
        
        await ctx.send(f"Commands will now only be allowed in this channel: {ctx.channel.mention}")
    
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

            song = {'title': title, 'url': audio_url, 'requester': ctx.author}

            if not voice_client.is_playing():
                # Play the song immediately if nothing is currently playing
                await self.play_song(ctx.guild, song, voice_client)
            else:
                # If a song is already playing, add it to the queue
                queue.append(song)
                embed = discord.Embed(
                    title="🎵 Added to Queue",
                    description=f"**{song['title']}** requested by {song['requester'].mention}",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Error downloading video: {e}")
            await ctx.send("There was an error downloading your video or searching for the song.")

    async def play_song(self, guild, song, voice_client, default_channel=None):
        audio_url = song['url']

        # Play the song using FFmpeg
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(audio_url))
        voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild)))

        # Fetch the allowed channel from Supabase
        allowed_channel_id = await self.fetch_allowed_channel(guild.id)
        allowed_channel = self.bot.get_channel(allowed_channel_id)

        # Fallback to the default channel if no allowed channel is set
        if allowed_channel is None and default_channel is not None:
            allowed_channel = default_channel

        # Log if no channel is found
        if allowed_channel is None:
            logging.error(f"No allowed channel found for guild {guild.id}")
            return

        # Send a message to indicate that the song is playing
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{song['title']}** requested by {song['requester'].mention}",
            color=discord.Color.green()
        )
        await allowed_channel.send(embed=embed)


    async def play_next(self, guild):
        voice_client = guild.voice_client
        queue = self.get_queue(guild)

        if len(queue) > 0:
            song = queue.pop(0)
            allowed_channel_id = await self.fetch_allowed_channel(guild.id)
            allowed_channel = self.bot.get_channel(allowed_channel_id)

            if allowed_channel is None:
                logging.error(f"No allowed channel found for guild {guild.id}")
            else:
                await self.play_song(guild, song, voice_client, allowed_channel)
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
            embed = discord.Embed(
                title="🎶 Current Queue",
                description="Here are the next songs in the queue:",
                color=discord.Color.green()
            )

            # Add each song in the queue as a field in the embed
            for index, song in enumerate(queue, start=1):
                embed.add_field(
                    name=f"{index}. {song['title']}",
                    value=f"Requested by {song['requester'].mention}",
                    inline=False
                )

            await ctx.send(embed=embed)
            
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