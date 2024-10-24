import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import logging
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import asyncio
from .music_controls import MusicControlView

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
        self.current_embed = None
        self.disconnect_timer = {}  
        self.updating_task = None

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
                voice_client = await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You need to be in a voice channel to play music.")
                return

        queue = self.get_queue(ctx.guild)

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]',
            'noplaylist': True,
            'quiet': True,
            'verbose': True,
        }

        try:
            # Check if the query is a URL
            if "youtube.com" in query or "youtu.be" in query:
                # Handle as a URL
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=False)  # Extract the info directly from the URL
                    audio_url = info['url']
                    title = info.get('title', 'Unknown Title')
                    duration = info.get('duration', None)  # Capture the duration
                    thumbnail = info.get('thumbnail', None)  # Thumbnail for embed
            else:
                # Treat as a search query
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    search_result = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                    audio_url = search_result['url']
                    title = search_result.get('title', 'Unknown Title')
                    duration = search_result.get('duration', None)
                    thumbnail = search_result.get('thumbnail', None)

            song = {
                'title': title,
                'url': audio_url,
                'requester': ctx.author,
                'duration': duration,
                'thumbnail': thumbnail
            }

            if not voice_client.is_playing():
                await self.play_song(ctx.guild, song, voice_client, ctx)
            else:
                queue.append(song)
                embed = discord.Embed(
                    title="🎵 Added to Queue",
                    description=f"**{song['title']}** requested by {song['requester'].mention}",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)

        except youtube_dl.utils.DownloadError as e:
            await ctx.send(f"Error processing the URL/query: {query}")
            logging.error(f"Error downloading or playing: {e}")


    async def play_song(self, guild, song, voice_client, ctx, default_channel=None):
        audio_url = song['url']

        try:
            self.current_ctx = ctx

            # Play the song using FFmpeg and call play_next after the song finishes
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(audio_url, before_options=FFMPEG_BEFORE_OPTS, options=FFMPEG_OPTS))
            voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild)))

            # Fetch the allowed channel from Supabase
            allowed_channel_id = await self.fetch_allowed_channel(guild.id)
            allowed_channel = self.bot.get_channel(int(allowed_channel_id))

            # Fallback to the default channel if no allowed channel is set
            if allowed_channel is None and default_channel is not None:
                allowed_channel = default_channel

            # Log if no channel is found
            if allowed_channel is None:
                logging.error(f"No allowed channel found for guild {guild.id}")
                return

            # Extract additional info about the song
            song_duration = song.get('duration', None)  # Duration in seconds if available
            if song_duration:
                minutes, seconds = divmod(song_duration, 60)
                duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = "Unknown duration"

            # Create the embed with additional info
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**[{song['title']}]({audio_url})**",
                color=discord.Color.green()
            )
            embed.add_field(name="Requested By", value=song['requester'].mention, inline=True)
            embed.add_field(name="Duration", value=duration_str, inline=True)

            # Add a thumbnail if the song has one (e.g., from YouTube)
            if song.get('thumbnail'):
                embed.set_thumbnail(url=song['thumbnail'])

            # Add footer with the requester's avatar
            embed.set_footer(text=f"Requested by: {song['requester'].display_name}", icon_url=ctx.author.avatar.url)

            view = MusicControlView(self.bot, ctx, voice_client)

            # Send the embed message with buttons
            if self.current_embed:
                # If there's a previous "Now Playing" embed, reply to it with the new song info
                new_message = await self.current_embed.reply(embed=embed, view=view)
                # Delete the original "Now Playing" embed after replying to it
                await self.current_embed.delete()
            else:
                new_message = await allowed_channel.send(embed=embed, view=view)

            # Update self.current_embed to the new message
            self.current_embed = new_message

            # Start the hourglass progress animation
            if self.updating_task:
                self.updating_task.cancel()
            self.updating_task = self.bot.loop.create_task(self.update_embed_progress(song['title'], allowed_channel))

        except Exception as e:
            logging.error(f"Error playing audio from URL '{audio_url}': {e}")
            await self.send_error_message(guild, f"Could not play the song '{song['title']}' due to an error.")
            await self.play_next(guild)  # Automatically play the next song on error



    async def update_embed_progress(self, title, allowed_channel):
        sand_timer_frames = ["⏳", "⌛", "⏳", "⌛"]  # Hourglass animation frames
        current_index = 0
        total_frames = len(sand_timer_frames)

        # Get the existing embed details (title, description, fields, etc.)
        original_embed = self.current_embed.embeds[0]  # Get the first embed

        while True:
            if current_index >= total_frames:
                current_index = 0  # Reset the animation cycle

            # Create a copy of the original embed to update the hourglass without modifying other fields
            embed = discord.Embed(
                title=original_embed.title,
                description=original_embed.description,
                color=original_embed.color
            )

            # Copy all fields from the original embed
            for field in original_embed.fields:
                embed.add_field(name=field.name, value=field.value, inline=field.inline)
        
            embed.description += f"\n\n{sand_timer_frames[current_index]}"
            embed.set_thumbnail(url=original_embed.thumbnail.url if original_embed.thumbnail else None)
            embed.set_footer(text=original_embed.footer.text, icon_url=original_embed.footer.icon_url)

            await self.current_embed.edit(embed=embed)

            current_index += 1
            await asyncio.sleep(1.5)  # Regular interval of 1.5 seconds




    async def play_next(self, guild):
        if self.updating_task:
            self.updating_task.cancel()  # Stop updating the current embed

        voice_client = guild.voice_client
        queue = self.get_queue(guild)

        if len(queue) > 0:
            song = queue.pop(0)

            # Use the stored context for the next song
            ctx = self.current_ctx  

            await self.play_song(guild, song, voice_client, ctx)
        else:
            # No more songs in the queue, disconnect after a timeout
            await self.wait_before_disconnect(guild, voice_client)


    async def cancel_disconnect(self, guild):
        if guild.id in self.disconnect_timer:
            self.disconnect_timer[guild.id].cancel()  # Cancel the scheduled disconnect
            logging.info(f"Disconnect timer canceled in guild {guild.id} due to song being added.")
            del self.disconnect_timer[guild.id]

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

    async def send_error_message(self, guild, message):
        allowed_channel_id = await self.fetch_allowed_channel(guild.id)
        allowed_channel = self.bot.get_channel(int(allowed_channel_id)) if allowed_channel_id else None

        if allowed_channel:
            embed = discord.Embed(
                title="⚠️ Error",
                description=message,
                color=discord.Color.red()
            )
            await allowed_channel.send(embed=embed)

    @commands.command(name="pause")
    async def pause(self, ctx):
        if not await self.check_channel(ctx):
            return

        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            embed = discord.Embed(
                title="⏸️ Paused",
                description="The song has been paused. Use `!resume` to continue playing.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No song is currently playing.")

    @commands.command(name="resume")
    async def resume(self, ctx):
        if not await self.check_channel(ctx):
            return

        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            embed = discord.Embed(
                title="▶️ Resumed",
                description="The song has been resumed.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No song is currently paused.")


async def setup(bot):
    await bot.add_cog(Music(bot))