import json
import os
import discord
from discord.ext import commands
import pytz
from datetime import datetime

class ModerationEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open('secrets.json') as config_file:
            self.config = json.load(config_file)
        self.chat_logs_dir = "chat_logs"
        if not os.path.exists(self.chat_logs_dir):
            os.makedirs(self.chat_logs_dir)
        self.timezone = pytz.timezone(self.config["TIMEZONE"])

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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        role_id = int(self.config["NEW_USER_JOIN_ROLE_ID"])
        role = discord.utils.get(member.guild.roles, id=role_id)
        if role:
            await member.add_roles(role)
            print(f"Added {role.name} to {member.name}.")
        else:
            print(f"User {member.name} joined the server, but role with ID {role_id} not found.")

        # Log the join event
        join_time = datetime.now(self.timezone)
        embed = discord.Embed(
            title="Member Joined",
            description=f"{member.mention} has joined the server.",
            color=discord.Color.green(),
            timestamp=join_time
        )
        embed.add_field(name="User ID", value=member.id, inline=False)

        logs_channel_id = int(self.config["LOGS_CHANNEL_ID"])
        logs_channel = self.bot.get_channel(logs_channel_id)  # Get the logs channel
        if not logs_channel:
            print(f"Logs channel with ID {logs_channel_id} not found.")
            return

        await logs_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Log the leave event
        leave_time = datetime.now(self.timezone)
        embed = discord.Embed(
            title="Member Left",
            description=f"{member.mention} has left the server.",
            color=discord.Color.red(),
            timestamp=leave_time
        )
        embed.add_field(name="User ID", value=member.id, inline=False)

        logs_channel_id = int(self.config["LOGS_CHANNEL_ID"])
        logs_channel = self.bot.get_channel(logs_channel_id)  # Get the logs channel
        if not logs_channel:
            print(f"Logs channel with ID {logs_channel_id} not found.")
            return

        await logs_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return  # Ignore messages from bots

        channel_id = str(message.channel.id)
        message_log = self.load_message_log(channel_id)

        # Convert the message's created_at timestamp to the specified timezone
        created_at_pacific = message.created_at.astimezone(self.timezone)

        message_data = {
            "author_id": str(message.author.id),
            "author_name": message.author.name,
            "channel_id": channel_id,
            "channel_name": message.channel.name,
            "content": message.content,
            "created_at": created_at_pacific.strftime('%Y-%m-%d %H:%M:%S'),
            "jump_url": message.jump_url
        }

        message_log[str(message.id)] = message_data
        self.save_message_log(channel_id, message_log)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        message_id = str(payload.message_id)
        channel_id = str(payload.channel_id)
        message_log = self.load_message_log(channel_id)

        if message_id not in message_log:
            print(f"Message with ID {message_id} not found in the log for channel {channel_id}.")
            return

        message_data = message_log[message_id]

        guild_id = str(payload.guild_id)
        guild = self.bot.get_guild(int(guild_id))  # Get the guild
        if not guild:
            print(f"Guild with ID {guild_id} not found.")
            return

        channel = guild.get_channel(int(channel_id))  # Get the channel
        if not channel:
            print(f"Channel with ID {channel_id} not found.")
            return

        try:
            message = await channel.fetch_message(int(message_id))  # Fetch the message
        except discord.NotFound:
            print(f"Message with ID {message_id} not found.")
            return

        if message.author.bot:
            return  # Ignore messages from bots

        if message_data["content"] == message.content:
            return  # Ignore if the content hasn't changed

        # Convert the message's edited_at timestamp to the specified timezone
        edited_at_pacific = message.edited_at.astimezone(self.timezone)

        embed = discord.Embed(
            title="Message Edited",
            color=discord.Color.og_blurple(),
            timestamp=edited_at_pacific
        )
        embed.add_field(name="Author", value=message.author.mention, inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=False)
        embed.add_field(name="Original Content", value=message_data["content"], inline=False)
        embed.add_field(name="Edited Content", value=message.content, inline=False)
        embed.add_field(name="Message Link", value=message.jump_url, inline=False)

        logs_channel_id = int(self.config["LOGS_CHANNEL_ID"])
        logs_channel = self.bot.get_channel(logs_channel_id)  # Get the logs channel
        if not logs_channel:
            print(f"Logs channel with ID {logs_channel_id} not found.")
            return

        await logs_channel.send(embed=embed)

        # Update the message log
        message_data["content"] = message.content
        message_data["edited_at"] = edited_at_pacific.strftime('%Y-%m-%d %H:%M:%S')
        self.save_message_log(channel_id, message_log)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        message_id = str(payload.message_id)
        channel_id = str(payload.channel_id)
        message_log = self.load_message_log(channel_id)

        if message_id not in message_log:
            print(f"Message with ID {message_id} not found in the log for channel {channel_id}.")
            return

        message_data = message_log[message_id]

        # Use the current time for the timestamp
        current_time = datetime.now(self.timezone)

        embed = discord.Embed(
            title="Message Deleted",
            color=discord.Color.blurple(),
            timestamp=current_time
        )
        embed.add_field(name="Author", value=f"<@{message_data['author_id']}>", inline=False)
        embed.add_field(name="Channel", value=f"<#{message_data['channel_id']}>", inline=False)
        embed.add_field(name="Original Timestamp", value=message_data["created_at"], inline=False)
        embed.add_field(name="Content", value=message_data["content"], inline=False)  # Use content from the log

        logs_channel_id = int(self.config["LOGS_CHANNEL_ID"])
        logs_channel = self.bot.get_channel(logs_channel_id)  # Get the logs channel
        if not logs_channel:
            print(f"Logs channel with ID {logs_channel_id} not found.")
            return

        await logs_channel.send(embed=embed)

        # Remove the message from the log
        del message_log[message_id]
        self.save_message_log(channel_id, message_log)

async def setup(bot):
    await bot.add_cog(ModerationEvents(bot))
