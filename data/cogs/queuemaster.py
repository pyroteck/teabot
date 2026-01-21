import discord
from discord.ext import commands
import sqlite3
import os
import json
import asyncio

class QueueMaster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.queue_dir = "queue_files"
        if not os.path.exists(self.queue_dir):
            os.makedirs(self.queue_dir)

        self.db_path = os.path.join(self.queue_dir, "queue_system.db")
        self.message_id_file = os.path.join(self.queue_dir, "queue_puller_message_id.txt")
        self.init_database()
        self.load_secrets()
        self.bot.loop.create_task(self.setup_puller_message())
        self.bot.loop.create_task(self.refresh_queue_loop())

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

    async def get_queue_users(self):
        """Get all users in queue ordered by join time"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_subscriber FROM queue_users ORDER BY joined_at ASC")
        users = cursor.fetchall()
        conn.close()
        return users

    async def get_user_position(self, user_id):
        """Get the user's position in the queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM queue_users WHERE joined_at <= (SELECT joined_at FROM queue_users WHERE user_id = ?)", (user_id,))
        position = cursor.fetchone()[0]
        conn.close()
        return position

    async def pull_top_user(self):
        """Pull the user at the top of the queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username FROM queue_users ORDER BY joined_at ASC LIMIT 1")
        user = cursor.fetchone()
        if user:
            user_id, username = user
            cursor.execute("DELETE FROM queue_users WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
            return user_id, username
        conn.close()
        return None, None

    async def pull_top_subscriber(self):
        """Pull the user at the top of the subscriber queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username FROM queue_users WHERE is_subscriber=1 ORDER BY joined_at ASC LIMIT 1")
        user = cursor.fetchone()
        if user:
            user_id, username = user
            cursor.execute("DELETE FROM queue_users WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
            return user_id, username
        conn.close()
        return None, None

    async def remove_user_from_queue(self, user_id):
        """Remove a specific user from the queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()

    def is_queue_disabled(self):
        """Check if queue is disabled"""
        disable_file = os.path.join(self.queue_dir, "disablequeue")
        return os.path.exists(disable_file)

    async def toggle_queue_status(self):
        """Toggle queue status (disable/enable)"""
        disable_file = os.path.join(self.queue_dir, "disablequeue")

        if self.is_queue_disabled():
            # Enable queue - remove disable file
            if os.path.exists(disable_file):
                os.remove(disable_file)
            return False  # Queue is enabled
        else:
            # Disable queue - create disable file
            with open(disable_file, 'w') as f:
                f.write("Queue disabled")
            return True  # Queue is disabled

    async def update_puller_message(self, channel_id, message_id):
        """Update the puller message with current queue list"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return

            message = await channel.fetch_message(message_id)
            users = await self.get_queue_users()

            # Create or update embed with queue list
            embed = message.embeds[0] if message.embeds else discord.Embed()
            embed.title = "Queue Master"
            embed.description = "Select an action below"

            # Clear existing queue fields if they exist
            embed.clear_fields()

            all_users = []
            subscriber_users = []

            for user in users:
                user_id, username, is_subscriber = user
                if is_subscriber:
                    subscriber_users.append(f"{username}")
                all_users.append(f"{username}")

            # Add regular queue field
            if all_users:
                regular_queue = "\n".join([f"{i+1}. {user}" for i, user in enumerate(all_users)])
                embed.add_field(name="Regular Queue", value=regular_queue, inline=True)
            else:
                embed.add_field(name="Regular Queue", value="No regular users in queue", inline=True)

            # Add subscriber queue field
            if subscriber_users:
                subscriber_queue = "\n".join([f"{i+1}. {user}" for i, user in enumerate(subscriber_users)])
                embed.add_field(name="Subscriber Queue", value=subscriber_queue, inline=True)
            else:
                embed.add_field(name="Subscriber Queue", value="No subscribers in queue", inline=True)

            # Create the view with correct button state
            view = MasterView(self, channel_id)
            view.message_id = message_id

            # Set the correct button label based on current queue status
            if self.is_queue_disabled():
                view.toggle_queue_button.label = "Enable Queue"
                view.toggle_queue_button.style = discord.ButtonStyle.success
            else:
                view.toggle_queue_button.label = "Disable Queue"
                view.toggle_queue_button.style = discord.ButtonStyle.danger

            await message.edit(embed=embed, view=view)
        except Exception as e:
            print(f"Error updating puller message: {e}")

    async def setup_puller_message(self):
        """Set up the puller message on bot startup"""
        await self.bot.wait_until_ready()

        # Pull channel ID from secrets
        channel_id = self.secrets.get("QUEUE_MASTER_CHANNEL_ID")
        if not channel_id:
            print("QUEUE_MASTER_CHANNEL_ID not found in secrets file!")
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

        # Delete any existing puller message
        await self.delete_existing_puller_message(channel)

        # Create new puller message
        await self.create_new_puller_message(channel, channel_id)

    async def delete_existing_puller_message(self, channel):
        """Delete any existing puller message in the channel"""
        try:
            # Read the stored message ID
            message_id = self.load_message_id()
            if message_id:
                try:
                    # Try to delete the old message
                    old_message = await channel.fetch_message(message_id)
                    await old_message.delete()
                    print(f"Deleted old puller message {message_id}")
                except discord.NotFound:
                    # Message doesn't exist, that's fine
                    pass
                except discord.Forbidden:
                    # No permission to delete, that's fine
                    print("No permission to delete old puller message")
                # Clear the stored message ID
                self.save_message_id(None)
        except Exception as e:
            print(f"Error deleting existing puller message: {e}")

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

    async def create_new_puller_message(self, channel, channel_id):
        """Create a new puller message and save its ID"""
        # Create embed message
        embed = discord.Embed(
            title="Queue Master",
            description="Select an action below to pull users from queue",
            color=discord.Color.blue()
        )

        # Add empty queue fields
        embed.add_field(name="User Queue", value="No users in queue", inline=True)
        embed.add_field(name="Subscriber Queue", value="No subscribers in queue", inline=True)

        # Create view with buttons
        view = MasterView(self, channel_id)
        message = await channel.send(embed=embed, view=view)

        # Store the message ID for later updates
        view.message_id = message.id
        self.save_message_id(message.id)
        print(f"New puller message created with ID {message.id}")

    async def refresh_queue_loop(self):  # Fixed: was missing 'self' parameter
        """Refresh queue every 5 seconds"""
        await self.bot.wait_until_ready()
        while True:
            try:
                # Get channel ID from secrets
                channel_id = self.secrets.get("QUEUE_MASTER_CHANNEL_ID")
                if not channel_id:
                    await asyncio.sleep(5)
                    continue

                try:
                    channel_id = int(channel_id)
                except ValueError:
                    await asyncio.sleep(5)
                    continue

                # Load message ID
                message_id = self.load_message_id()
                if message_id:
                    await self.update_puller_message(channel_id, message_id)
                else:
                    # If no message ID, try to recreate
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await self.delete_existing_puller_message(channel)
                        await self.create_new_puller_message(channel, channel_id)
            except Exception as e:
                print(f"Error in refresh loop: {e}")
            await asyncio.sleep(5)

class MasterView(discord.ui.View):
    def __init__(self, cog, channel_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id
        self.message_id = None

    @discord.ui.button(label="Pull Top of Queue", style=discord.ButtonStyle.success)
    async def pull_top_button(self, interaction, button):
        """Pull the top user from queue"""
        user_id, username = await self.cog.pull_top_user()

        if user_id:
            # Send direct message to user
            try:
                user = await self.cog.bot.fetch_user(user_id)
                dm_channel = await user.create_dm()
                await dm_channel.send(f"It's your turn to play! Please check in with Chai!")
            except:
                print(f"Failed to send DM to user '{username}'")

            await interaction.response.send_message(
                f"Picked `{username}` from the queue!",
                ephemeral=True
            )

            await self.cog.update_puller_message(self.channel_id, self.message_id)
        else:
            await interaction.response.send_message("No users in queue.", ephemeral=True)

    @discord.ui.button(label="Pull Top of Subscriber Queue", style=discord.ButtonStyle.primary)
    async def pull_top_subscriber_button(self, interaction, button):
        """Pull the top subscriber from queue"""

        user_id, username = await self.cog.pull_top_subscriber()
        if user_id:
            try:
                user = await self.cog.bot.fetch_user(user_id)
                dm_channel = await user.create_dm()
                await dm_channel.send(f"It's your turn to play! Please check in with Chai!")
            except:
                pass  # Ignore errors if DM fails

            await interaction.response.send_message(
                f"Picked subscriber `{username}` from the queue!",
                ephemeral=True
            )

            await self.cog.update_puller_message(self.channel_id, self.message_id)
        else:
            await interaction.response.send_message("No subscribers in queue.", ephemeral=True)

    @discord.ui.button(label="Pick from Queue", style=discord.ButtonStyle.secondary)
    async def pick_from_queue_button(self, interaction, button):
        """Open dropdown to pick user from queue"""
        users = await self.cog.get_queue_users()

        if not users:
            await interaction.response.send_message(
                "No users in queue to pick from!",
                ephemeral=True
            )
            return

        # Create dropdown view
        dropdown_view = UserSelectView(self.cog, users, self.channel_id, self.message_id)
        dropdown_embed = discord.Embed(
            title="Select User to Pull",
            description="Choose a user from the queue to pull",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=dropdown_embed, view=dropdown_view, ephemeral=True)

    @discord.ui.button(label="Disable Queue", style=discord.ButtonStyle.danger)
    async def toggle_queue_button(self, interaction, button):
        """Toggle queue status"""
        # Toggle queue status
        is_disabled = await self.cog.toggle_queue_status()

        # Create new view with updated button state
        new_view = MasterView(self.cog, self.channel_id)
        new_view.message_id = self.message_id

        # Update button label and style based on current state
        if is_disabled:
            new_view.toggle_queue_button.label = "Enable Queue"
            new_view.toggle_queue_button.style = discord.ButtonStyle.success
        else:
            new_view.toggle_queue_button.label = "Disable Queue"
            new_view.toggle_queue_button.style = discord.ButtonStyle.danger

        # Update the message with new view
        await interaction.response.edit_message(view=new_view)
        await interaction.followup.send(f"Queue has been {'disabled' if is_disabled else 'enabled'}", ephemeral=True)

    @discord.ui.button(label="Clear Queue", style=discord.ButtonStyle.danger)
    async def clear_queue_button(self, interaction, button):
        """Clear the entire queue with confirmation"""
        # Create confirmation view
        confirm_view = ConfirmClearView(self.cog, self.channel_id, self.message_id)
        confirm_embed = discord.Embed(
            title="Confirm Queue Clear",
            description="Are you sure you want to clear the entire queue? This action cannot be undone.",
            color=discord.Color.red()
        )

        await interaction.response.send_message(
            embed=confirm_embed,
            view=confirm_view,
            ephemeral=True
        )

class ConfirmClearView(discord.ui.View):
    def __init__(self, cog, channel_id, message_id):
        super().__init__(timeout=30)
        self.cog = cog
        self.channel_id = channel_id
        self.message_id = message_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm_clear_button(self, interaction, button):
        """Confirm and clear the queue"""
        # Clear the database
        conn = sqlite3.connect(self.cog.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users")
        conn.commit()
        conn.close()

        # Update the puller message
        await self.cog.update_puller_message(self.channel_id, self.message_id)

        # Edit the original message instead of sending a new one
        await interaction.response.edit_message(
            content="Queue has been cleared successfully!",
            embed=None,
            view=None  # Remove the buttons after action is completed
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.success)
    async def cancel_clear_button(self, interaction, button):
        """Cancel the clear operation"""
        # Edit the original message instead of sending a new one
        await interaction.response.edit_message(
            content="Queue clear operation cancelled.",
            embed=None,
            view=None  # Remove the buttons after action is completed
        )

class UserSelectView(discord.ui.View):
    def __init__(self, cog, users, channel_id, message_id):
        super().__init__(timeout=30)
        self.cog = cog
        self.users = users
        self.channel_id = channel_id
        self.message_id = message_id

        # Create dropdown options
        options = []
        for user_id, username, is_subscriber in users:
            options.append(discord.SelectOption(
                label=username,
                value=str(user_id),
                description=f"Pull {username}"
            ))

        # Create dropdown
        self.dropdown = discord.ui.Select(
            placeholder="Choose a user...",
            options=options,
            min_values=1,
            max_values=None
        )
        self.dropdown.callback = self.dropdown_callback
        self.add_item(self.dropdown)

    async def dropdown_callback(self, interaction):
        """Handle dropdown selection"""
        user_id = int(self.dropdown.values[0])
        username = next((user[1] for user in self.users if user[0] == user_id), None)

        if username:
            # Remove user from queue
            await self.cog.remove_user_from_queue(user_id)

            # Send direct message to user
            try:
                user = await self.cog.bot.fetch_user(user_id)
                dm_channel = await user.create_dm()
                await dm_channel.send(f"It's your turn to play! Please check in with Chai!")
            except:
                pass  # Ignore if can't send DM

            # Update message
            await interaction.response.edit_message(
                content=f"Picked `{username}` from the queue!",
                view=None,
                embed=None
            )

            # Update puller message
            await self.cog.update_puller_message(self.channel_id, self.message_id)
        else:
            await interaction.response.edit_message(
                content="User not found!",
                view=None,
                embed=None
            )

# Event listener for queue updates
@commands.Cog.listener()
async def on_queue_update(self):
    """Event to update puller message when queue changes"""
    pass

async def setup(bot):
    await bot.add_cog(QueueMaster(bot))
