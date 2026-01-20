import discord
from discord.ext import commands
import sqlite3
import os
import json

class QueueSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "queue_system.db"
        self.message_id_file = "queue_message_id.txt"
        self.init_database()
        self.load_secrets()
        self.bot.loop.create_task(self.setup_queue_message())
        self.user_response_messages = {}  # Track user response messages for editing

    def load_secrets(self):
        """Load secrets from JSON file"""
        try:
            with open('secrets.json', 'r') as f:
                self.secrets = json.load(f)
        except FileNotFoundError:
            print("Secrets file not found!")
            self.secrets = {}

    def init_database(self):
        """Initialize the SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS queue_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_subscriber BOOLEAN,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()
        conn.close()

    async def get_queue_count(self):
        """Get the current queue count"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM queue_users")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    async def get_user_position(self, user_id):
        """Get the user's position in the queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM queue_users WHERE joined_at <= (SELECT joined_at FROM queue_users WHERE user_id = ?)", (user_id,))
        position = cursor.fetchone()[0]
        conn.close()
        return position

    async def is_user_twitch_sub(self, user_id, guild):
        """Check if user has the Twitch subscriber role"""
        twitch_sub_role_id = self.secrets.get("TWITCH_SUB_ROLE_ID")
        if not twitch_sub_role_id:
            return False

        try:
            twitch_sub_role_id = int(twitch_sub_role_id)
        except ValueError:
            return False

        member = guild.get_member(user_id)
        if not member:
            return False

        return twitch_sub_role_id in [role.id for role in member.roles]

    async def update_queue_message(self, channel_id, message_id):
        """Update the queue message with current count"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return

            message = await channel.fetch_message(message_id)

            # Get current queue count
            count = await self.get_queue_count()

            # Update embed with new count
            embed = message.embeds[0] if message.embeds else discord.Embed()
            embed.title = f"Game Queue - {count} players"
            embed.description = "Click the buttons below to join or leave the queue"

            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating queue message: {e}")

    async def setup_queue_message(self):
        """Set up the queue message on bot startup"""
        await self.bot.wait_until_ready()

        # Pull channel ID from secrets
        channel_id = self.secrets.get("QUEUE_CHANNEL_ID")
        if not channel_id:
            print("QUEUE_CHANNEL_ID not found in secrets file!")
            return

        try:
            channel_id = int(channel_id)
        except ValueError:
            print("Invalid channel ID in secrets file!")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Channel with ID {channel_id} not found!")
            return

        # Delete any existing queue message first
        await self.delete_existing_queue_message(channel)

        # Create new queue message
        await self.create_new_queue_message(channel, channel_id)

    async def delete_existing_queue_message(self, channel):
        """Delete any existing queue message in the channel"""
        try:
            # Read the stored message ID
            message_id = self.load_message_id()
            if message_id:
                try:
                    # Try to delete the old message
                    old_message = await channel.fetch_message(message_id)
                    await old_message.delete()
                    print(f"Deleted old queue message {message_id}")
                except discord.NotFound:
                    # Message doesn't exist, that's fine
                    pass
                except discord.Forbidden:
                    # No permission to delete, that's fine
                    print("No permission to delete old queue message")
                # Clear the stored message ID
                self.save_message_id(None)
        except Exception as e:
            print(f"Error deleting existing queue message: {e}")

    def load_message_id(self):
        """Load the stored message ID from file"""
        try:
            if os.path.exists(self.message_id_file):
                with open(self.message_id_file, 'r') as f:
                    content = f.read().strip()
                    return int(content) if content else None
        except Exception as e:
            print(f"Error loading message ID: {e}")
        return None

    def save_message_id(self, message_id):
        """Save the message ID to file"""
        try:
            with open(self.message_id_file, 'w') as f:
                f.write(str(message_id) if message_id else "")
        except Exception as e:
            print(f"Error saving message ID: {e}")

    async def create_new_queue_message(self, channel, channel_id):
        """Create a new queue message and save its ID"""
        # Create embed message
        embed = discord.Embed(
            title="Game Queue - 0 players",
            description="Click the buttons below to join or leave the queue",
            color=discord.Color.blue()
        )

        # Create view with buttons
        view = QueueView(self, channel_id)
        message = await channel.send(embed=embed, view=view)

        # Store the message ID for later updates
        view.message_id = message.id
        self.save_message_id(message.id)
        print(f"New queue message created with ID {message.id}")

        # Update the message to show current count
        await self.update_queue_message(channel_id, message.id)

    @commands.command(name="createqueue")
    async def create_queue(self, ctx):
        """Create a queue system using the channel ID from secrets"""
        # Pull channel ID from secrets
        channel_id = self.secrets.get("QUEUE_CHANNEL_ID")
        if not channel_id:
            await ctx.send("QUEUE_CHANNEL_ID not found in secrets file!")
            return

        try:
            channel_id = int(channel_id)
        except ValueError:
            await ctx.send("Invalid channel ID in secrets file!")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send(f"Channel with ID {channel_id} not found!")
            return

        # Delete any existing queue message and create a new one
        await self.delete_existing_queue_message(channel)
        await self.create_new_queue_message(channel, channel_id)
        await ctx.send(f"Queue created in <#{channel_id}>")

class QueueView(discord.ui.View):  # Changed to inherit from View
    def __init__(self, cog, channel_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id
        self.message_id = None

    async def send_user_response(self, interaction, message_content, ephemeral=True, delete_after_secs=None):
        """Send a response to user, editing previous ephemeral messages if they exist"""
        user_id = interaction.user.id

        # Check if we have an existing ephemeral message for this user
        if user_id in self.cog.user_response_messages:
            try:
                # Edit the existing ephemeral message
                existing_message = self.cog.user_response_messages[user_id]
                await existing_message.edit(content=message_content)
                return existing_message
            except:
                # If editing fails, create a new one
                pass

        # Create new ephemeral message
        response_message = await interaction.response.send_message(
            content=message_content,
            ephemeral=True,
            delete_after=delete_after_secs
        )
        # Store the message reference for future edits
        self.cog.user_response_messages[user_id] = response_message
        return response_message

    @discord.ui.button(label="Join Queue", style=discord.ButtonStyle.success)
    async def join_button(self, interaction, button):
        """Handle joining the queue"""
        user_id = interaction.user.id
        username = interaction.user.name
        guild = interaction.guild

        # Check if user already has a response message
        if user_id in self.cog.user_response_messages:
            try:
                existing_message = self.cog.user_response_messages[user_id]
                await existing_message.edit(content="Attempting to join queue...")
            except:
                pass

        # Check if user is already in queue
        conn = sqlite3.connect(self.cog.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM queue_users WHERE user_id=?", (user_id,))
        existing_user = cursor.fetchone()

        if existing_user:
            await self.send_user_response(
                interaction,
                "You're already in the queue!",
                ephemeral=True,
                delete_after_secs=5.0
            )
            conn.close()
            return

        # Check if user is a Twitch subscriber
        is_subscriber = await self.cog.is_user_twitch_sub(user_id, guild)

        # Add user to queue
        cursor.execute(
            "INSERT INTO queue_users (user_id, username, is_subscriber) VALUES (?, ?, ?)",
            (user_id, username, is_subscriber)
        )
        conn.commit()
        conn.close()

        # Update queue message
        await self.cog.update_queue_message(self.channel_id, self.message_id)

        # Send success message
        if is_subscriber:
            await self.send_user_response(
                interaction,
                "You've been added to the queue as a Twitch subscriber!",
                ephemeral=True,
                delete_after_secs=5.0
            )
        else:
            await self.send_user_response(
                interaction,
                "You've been added to the queue!",
                ephemeral=True,
                delete_after_secs=5.0
            )

    @discord.ui.button(label="Leave Queue", style=discord.ButtonStyle.danger)
    async def leave_button(self, interaction, button):
        """Handle leaving the queue with confirmation"""
        user_id = interaction.user.id

        # Check if user is actually in the queue before showing confirmation
        conn = sqlite3.connect(self.cog.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM queue_users WHERE user_id=?", (user_id,))
        existing_user = cursor.fetchone()
        conn.close()

        if not existing_user:
            await self.send_user_response(
                interaction,
                "You are not currently in the queue!",
                ephemeral=True,
                delete_after_secs=5.0
            )
            return

        # Create confirmation view with orange embed
        confirm_view = ConfirmView(self.cog, user_id, self.channel_id, self.message_id)
        confirm_embed = discord.Embed(
            title="Confirm Leave",
            description="Are you sure you want to leave the queue?",
            color=discord.Color.orange()  # Orange bar for confirmation
        )

        # Send confirmation message
        await interaction.response.send_message(
            embed=confirm_embed,
            view=confirm_view,
            ephemeral=True
        )

    @discord.ui.button(label="Check My Place", style=discord.ButtonStyle.primary)
    async def check_place_button(self, interaction, button):
        """Handle checking user's place in queue"""
        user_id = interaction.user.id

        # Get user's position in queue
        position = await self.cog.get_user_position(user_id)
        total_count = await self.cog.get_queue_count()

        if position == 0:
            await self.send_user_response(
                interaction,
                "You are not in the queue!",
                ephemeral=True,
                delete_after_secs=5.0
            )
        else:
            # Format the response based on position
            if position == 1:
                place_text = "1st"
            elif position == 2:
                place_text = "2nd"
            elif position == 3:
                place_text = "3rd"
            else:
                place_text = f"{position}th"

            await self.send_user_response(
                interaction,
                f"You are currently {place_text} place in line out of {total_count} players in the queue.",
                ephemeral=True,
                delete_after_secs=5.0
            )

class ConfirmView(discord.ui.View):
    def __init__(self, cog, user_id, channel_id, message_id):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.channel_id = channel_id
        self.message_id = message_id

    @discord.ui.button(label="Yes, Leave", style=discord.ButtonStyle.danger)
    async def confirm_leave(self, interaction, button):
        """Confirm leaving the queue"""
        # Remove user from queue
        conn = sqlite3.connect(self.cog.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE user_id=?", (self.user_id,))
        conn.commit()
        conn.close()

        # Update the response embed to show success
        try:
            success_embed = discord.Embed(
                title="Successfully Left Queue",
                description="You have been removed from the queue.",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=success_embed, view=None, delete_after=5.0)
            
            # Update the main queue message
            await self.cog.update_queue_message(self.channel_id, self.message_id)
        except:
            await interaction.response.edit_message(content="Successfully left the queue.", view=None, delete_after=5.0)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_leave(self, interaction, button):
        """Cancel leaving the queue"""
        try:
            cancel_embed = discord.Embed(
                title="Cancelled Leaving Queue",
                description="You are still in the queue.",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=cancel_embed, view=None, delete_after=5.0)
        except:
            await interaction.response.edit_message(content="Cancelled leaving the queue.", view=None, delete_after=5.0)

async def setup(bot):
    await bot.add_cog(QueueSystem(bot))
