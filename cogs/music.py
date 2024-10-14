import discord
from discord.ext import commands
import youtube_dl 

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

class Music(commands.Cog):
    def __init__(self,bot):
        self.bot = bot
    
    @commands.command(name='join')
    async def join(self, ctx):
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            if not ctx.voice_client:
                await channel.connect()
            else:
                await ctx.voice_client.move_to(channel)
        else:
            await ctx.send("You must be in a voice channel.")
    
    @commands.command(name='play')
    async def play(self, ctx, url):
        voice_channel = ctx.author.voice.channel
        if not ctx.voice_client:
            await voice_channel.connect()
        else:
            await ctx.voice_client.move_to(voice_channel)

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['formats'][0]['url']

            voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
            voice.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=url2))

async def setup(bot):
    await bot.add_cog(Music(bot))