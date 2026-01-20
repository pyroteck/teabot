import discord
from discord.ext import commands
import sqlite3
import os
import json

class QueuePuller(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "queue_system.db"
        self.message_id_file = "queue_puller_message_id.txt"
        self.init_database()
        self.load_secrets()
        self.bot.loop.create_task(self.setup_puller_message())

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

    async def remove_user_from_queue(self, user_id):
        """Remove a specific user from the queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()

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
            embed.title = "Queue Puller"
            embed.description = "Select an action below to pull users from queue"

            # Clear existing queue field if exists
            embed.clear_fields()

            # Add updated queue list
            if users:
                queue_list = "\n".join([f"{i+1}. {user[1]}" for i, user in enumerate(users)])
                embed.add_field(name="Current Queue", value=queue_list, inline=False)
            else:
                embed.add_field(name="Current Queue", value="No users in queue", inline=False)

            await message.edit(embed=embed)
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
            title="Queue Puller",
            description="Select an action below to pull users from queue",
            color=discord.Color.blue()
        )

        # Add empty queue list field
        embed.add_field(name="Current Queue", value="No users in queue", inline=False)

        # Create view with buttons
        view = PullerView(self, channel_id)
        message = await channel.send(embed=embed, view=view)

        # Store the message ID for later updates
        view.message_id = message.id
        self.save_message_id(message.id)
        print(f"New puller message created with ID {message.id}")

        # Update the message to show current queue
        await self.update_puller_message(channel_id, message.id)

class PullerView(discord.ui.View):
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
                dm_channel = await interaction.user.create_dm()
                await dm_channel.send(f"You've been pulled from the queue! It's your turn to play!")
            except:
                pass  # Ignore if can't send DM

            # Update message
            await interaction.response.send_message(
                f"Pulled {username} from the queue!",
                ephemeral=True
            )

            # Update puller message
            await self.cog.update_puller_message(self.channel_id, self.message_id)
        else:
            await interaction.response.send_message(
                "No users in queue to pull!",
                ephemeral=True
            )

    @discord.ui.button(label="Pick from Queue", style=discord.ButtonStyle.primary)
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

        await interaction.response.send_message(
            embed=dropdown_embed,
            view=dropdown_view,
            ephemeral=True
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
                description=f"Pull {username}" if is_subscriber else f"Pull {username}"
            ))

        # Create dropdown
        self.dropdown = discord.ui.Select(
            placeholder="Choose a user...",
            options=options,
            min_values=1,
            max_values=1
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
                dm_channel = await interaction.user.create_dm()
                await dm_channel.send(f"You've been pulled from the queue! You're now in the game.")
            except:
                pass  # Ignore if can't send DM

            # Update message
            await interaction.response.send_message(
                f"Pulled {username} from the queue!",
                ephemeral=True
            )

            # Update puller message
            await self.cog.update_puller_message(self.channel_id, self.message_id)
        else:
            await interaction.response.send_message(
                "User not found!",
                ephemeral=True
            )

# Event listener for queue updates
@commands.Cog.listener()
async def on_queue_update(self):
    """Event to update puller message when queue changes"""
    pass

async def setup(bot):
    await bot.add_cog(QueuePuller(bot))
