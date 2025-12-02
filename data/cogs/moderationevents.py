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

        self.ignored_message_ids = set(self.config.get("IGNORED_MESSAGE_IDS", []))

        self.alternate_log_channels = {}
        alternate_log_config = self.config.get("ALTERNATE_LOG_CHANNEL", [])
        for mapping in alternate_log_config:
            if ':' in mapping:
                channel_id, message_ids_str = mapping.split(':', 1)
                channel_id = channel_id.strip()
                message_ids = [msg_id.strip() for msg_id in message_ids_str.split(',')]
                self.alternate_log_channels[channel_id] = set(message_ids)

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
        embed.add_field(name="Username", value=member.name, inline=False)
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
        embed.add_field(name="Username", value=member.name, inline=False)
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
        
        # Check list in secrets if there's a message ID to ignore
        if str(payload.message_id) in self.ignored_message_ids:
            print(f"Message with ID {message_id} was edited but is marked to be ignored.")
            return

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

        # Check if this message should go to an alternate channel
        alternate_channel_id = None
        for channel_id_key, message_ids in self.alternate_log_channels.items():
            if message_id in message_ids:
                alternate_channel_id = channel_id_key
                break

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

        if alternate_channel_id:
            logs_channel = self.bot.get_channel(int(alternate_channel_id))
            if logs_channel:
                await logs_channel.send(embed=embed)
            else:
                # Fallback to default channel if alternate channel is not found
                default_logs_channel_id = int(self.config["LOGS_CHANNEL_ID"])
                default_logs_channel = self.bot.get_channel(default_logs_channel_id)
                if default_logs_channel:
                    await default_logs_channel.send(embed=embed)
        else:
            # Send to default channel
            logs_channel_id = int(self.config["LOGS_CHANNEL_ID"])
            logs_channel = self.bot.get_channel(logs_channel_id)
            if logs_channel:
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
