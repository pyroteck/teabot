from datetime import datetime
import discord
from discord.ext import commands
import json
import os
import pytz

class ModerationCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open('secrets.json') as config_file:
            self.config = json.load(config_file)
        self.chat_logs_dir = "chat_logs"
        if not os.path.exists(self.chat_logs_dir):
            os.makedirs(self.chat_logs_dir)
        self.pacific_tz = pytz.timezone(self.config["TIMEZONE"])

    def get_message_log_file(self, channel_id):
        return os.path.join(self.chat_logs_dir, f"message_log_{channel_id}.json")

    def load_message_log(self, channel_id):
        file_path = self.get_message_log_file(channel_id)
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_message_log(self, channel_id, message_log):
        file_path = self.get_message_log_file(channel_id)
        with open(file_path, 'w') as f:
            json.dump(message_log, f, indent=4)

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def purgeafter(self, ctx, *, timestamp: str):
        """Deletes all messages after the specified date and time.

        Format the timestamp as 'YYYY-MM-DD HH:MM:SS'. Example: '2023-10-01 12:00:00'
        """
        try:
            # Convert the timestamp string to a datetime object
            after_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            after_time = pytz.utc.localize(after_time).astimezone(self.pacific_tz)
        except ValueError:
            await ctx.send("Invalid timestamp format. Please use 'YYYY-MM-DD HH:MM:SS'.")
            return

        # Get the channel where the command was invoked
        channel = ctx.channel

        # Delete messages after the specified time
        deleted_count = 0
        async for message in channel.history(after=after_time, oldest_first=True):
            await message.delete()
            deleted_count += 1

        await ctx.send(f"Deleted {deleted_count} messages after {after_time}.")

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def logeverymessage(self, ctx):
        """Logs the entire message history for every channel in the guild."""
        guild = ctx.guild
        total_messages_logged = 0

        for channel in guild.text_channels:
            channel_id = str(channel.id)
            message_log = self.load_message_log(channel_id)
            async for message in channel.history(limit=None, oldest_first=True):
                if message.author.bot:
                    continue  # Ignore messages from bots

                # Convert the message's created_at timestamp to the specified timezone
                created_at_pacific = message.created_at.astimezone(self.pacific_tz)

                message_data = {
                    "author_id": str(message.author.id),
                    "author_name": message.author.name,
                    "channel_id": channel_id,
                    "channel_name": channel.name,
                    "content": message.content,
                    "created_at": created_at_pacific.strftime('%Y-%m-%d %H:%M:%S'),
                    "jump_url": message.jump_url
                }

                if str(message.id) not in message_log:
                    message_log[str(message.id)] = message_data
                    total_messages_logged += 1

            self.save_message_log(channel_id, message_log)

        await ctx.send(f"Logged {total_messages_logged} messages across all channels.")
        
    @commands.hybrid_command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx):
        await self.bot.tree.sync()
        if isinstance(ctx.interaction, discord.Interaction):
             await ctx.reply('Command tree synced.', ephemeral=True)
        else:
             await ctx.reply('Command tree synced.')

async def setup(bot):
    await bot.add_cog(ModerationCommands(bot))
