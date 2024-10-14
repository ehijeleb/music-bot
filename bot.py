import discord
from discord.ext import commands
import os
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def load_cogs():
    await bot.load_extension("cogs.music")


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await load_cogs()  


bot.run(TOKEN)
