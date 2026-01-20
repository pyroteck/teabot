import discord
from discord.ext import commands
import json

intents = discord.Intents.all()

# Load configuration from secrets.json
with open('secrets.json') as config_file:
    config = json.load(config_file)

bot = commands.Bot(command_prefix='$', intents=intents)

async def load_extensions():
    for filename in ['d20', 'general', 'moderationcommands', 'moderationevents', 'stream', 'queue']:
        await bot.load_extension(f"cogs.{filename}")

@bot.event
async def on_ready():
    await load_extensions()
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('-----------------')
    stream_cog = bot.get_cog('Stream')
    if stream_cog:
        stream_cog.check_stream.start()

bot.run(config.get("CLIENT_TOKEN"))
