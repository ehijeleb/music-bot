import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import logging
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import asyncio

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
            # Try up to 5 search attempts
            for i in range(1, 6):
                try:
                    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                        # Use ytsearch to get a single result for each attempt
                        search_result = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]

                        audio_url = search_result['url']
                        title = search_result.get('title', 'Unknown Title')

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

                        return  # Exit the loop after a successful play

                except youtube_dl.utils.DownloadError as e:
                    # Log the error and move on to the next result
                    if 'Sign in to confirm your age' in str(e):
                        await ctx.send(f"Attempt {i} failed due to age restriction for: **{query}**")
                    else:
                        await ctx.send(f"Attempt {i} failed for: **{query}**")
                    logging.error(f"Error downloading or playing result {i} for query '{query}': {e}")

            # If all attempts fail, notify the user
            await ctx.send(f"All attempts to play **{query}** have failed.")

        except Exception as e:
            logging.error(f"Error during search or extraction: {e}")
            await ctx.send("There was an error performing the search.")

    async def play_song(self, guild, song, voice_client, default_channel=None):
        audio_url = song['url']

        try:
            # Play the song using FFmpeg
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

            # Send a message to indicate that the song is playing
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**{song['title']}** requested by {song['requester'].mention}",
                color=discord.Color.green()
            )
            self.current_embed = await allowed_channel.send(embed=embed)

            # Ensure that the embed is sent before updating
            if self.current_embed:
                if self.updating_task:
                    self.updating_task.cancel()
                self.updating_task = self.bot.loop.create_task(self.update_embed_progress(song['title'], allowed_channel))

        except Exception as e:
            logging.error(f"Error playing audio from URL '{audio_url}': {e}")
            await self.send_error_message(guild, f"Could not play the song '{song['title']}' due to an error.")
            await self.play_next(guild)  # Automatically play the next song on error



    async def update_embed_progress(self, title, allowed_channel):
        progress_bars = [
            "▶️───────────", "─▶️──────────", "──▶️─────────",
            "───▶️────────", "────▶️───────", "─────▶️──────",
            "──────▶️─────", "───────▶️────", "────────▶️───",
            "─────────▶️──", "──────────▶️─", "───────────▶️"
        ]
        current_index = 0
        total_bars = len(progress_bars)

        while True:
            if current_index >= total_bars:
                current_index = 0  # Reset the progress bar

            # Update the embed description with the new progress bar
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**{title}**\n\nProgress: [{progress_bars[current_index]}]",
                color=discord.Color.green()
            )
            await self.current_embed.edit(embed=embed)

            current_index += 1
            await asyncio.sleep(1)


    async def play_next(self, guild):
        if self.updating_task:
            self.updating_task.cancel()  # Stop updating the current embed

        voice_client = guild.voice_client
        queue = self.get_queue(guild)

        if len(queue) > 0:
            song = queue.pop(0)
            await self.play_song(guild, song, voice_client)
        else:
            # No more songs in the queue
            await self.wait_before_disconnect(guild, voice_client)

    async def wait_before_disconnect(self, guild, voice_client):
        logging.info(f"Queue is empty, starting 3-minute wait before disconnecting in guild {guild.id}.")
        
        def check_if_song_added():
            # Check if any new songs are added to the queue during the waiting period
            return len(self.get_queue(guild)) > 0

        try:
            # Store the task so it can be canceled if a new song is added
            self.disconnect_timer[guild.id] = self.bot.loop.create_task(asyncio.sleep(180))  # 3-minute wait

            # Wait for 3 minutes or until a song is added
            await asyncio.wait_for(self.disconnect_timer[guild.id], timeout=180)

            if check_if_song_added():
                logging.info(f"New song added, canceling disconnect timer in guild {guild.id}.")
                return  # A song was added, so don't disconnect

        except asyncio.TimeoutError:
            # Timeout (3 minutes have passed without any new songs being added)
            logging.info(f"Disconnecting from voice channel in guild {guild.id} due to inactivity.")
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
        finally:
            # Remove the disconnect timer entry after it's done
            if guild.id in self.disconnect_timer:
                del self.disconnect_timer[guild.id]

    async def cancel_disconnect(self, guild):
        """Cancel the disconnect timer if a song is added to the queue."""
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
        """Pauses the currently playing song."""
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
        """Resumes the currently paused song."""
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