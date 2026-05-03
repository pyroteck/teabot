import discord
from discord.ext import commands
import json
from datetime import datetime
import pytz

intents = discord.Intents.all()

# Load configuration from secrets.json
with open('secrets.json') as config_file:
    config = json.load(config_file)

bot = commands.Bot(command_prefix='$', intents=intents)
timezone = pytz.timezone(config["TIMEZONE"])

async def load_extensions():
    for filename in ['d20', 'general', 'moderationcommands', 'moderationevents', 'stream', 'queue', 'queuemaster']:
        await bot.load_extension(f"cogs.{filename}")

@bot.event
async def on_ready():
    await load_extensions()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Logged in as {bot.user} (ID: {bot.user.id})")
    print('-----------------')

    moderation_cog = bot.get_cog('ModerationCommands')
    if moderation_cog:
        await startup_logger(moderation_cog)

# Copy of logger commmand to run on every startup
async def startup_logger(moderation_cog):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running startup message logging...")

    for guild in moderation_cog.bot.guilds:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Processing messages for guild {guild.name}")
        total_messages_logged = 0

        for channel in guild.text_channels:
            channel_id = str(channel.id)
            message_log = moderation_cog.load_message_log(channel_id)
            channel_messages_logged = 0

            try:
                async for message in channel.history(limit=None, oldest_first=True):
                    if message.author.bot:
                        continue

                    created_at_tz = message.created_at.astimezone(timezone)

                    message_data = {
                        "author_id": str(message.author.id),
                        "author_name": message.author.name,
                        "channel_id": channel_id,
                        "channel_name": channel.name,
                        "content": message.content,
                        "created_at": created_at_tz.strftime('%Y-%m-%d %H:%M:%S'),
                        "jump_url": message.jump_url
                    }

                    if str(message.id) not in message_log:
                        message_log[str(message.id)] = message_data
                        total_messages_logged += 1
                        channel_messages_logged += 1

                moderation_cog.save_message_log(channel_id, message_log)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Logged {channel_messages_logged} messages for channel {channel.name}")

            except Exception as e:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error processing channel {channel.name}: {e}")

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Completed logging for guild {guild.name}. Total messages logged: {total_messages_logged}")

bot.run(config.get("CLIENT_TOKEN"))
