import asyncio
import datetime
import discord
import os
import sqlite3
import texttable
from discord.ext import commands
from secrets import SystemRandom

# Cooldown variable; change only for testing purposes
cooldown_sec = 3600

class D20(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_folder = "user_dbs"
        if not os.path.exists(self.db_folder):
            os.makedirs(self.db_folder)

    def get_db_path(self, user_id):
        return os.path.join(self.db_folder, f"{user_id}.db")

    def create_user_db(self, user_id):
        db_path = self.get_db_path(user_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Create roll results table with initial values
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roll_results (
                id INTEGER PRIMARY KEY,
                roll_1 INTEGER DEFAULT 0,
                roll_2 INTEGER DEFAULT 0,
                roll_3 INTEGER DEFAULT 0,
                roll_4 INTEGER DEFAULT 0,
                roll_5 INTEGER DEFAULT 0,
                roll_6 INTEGER DEFAULT 0,
                roll_7 INTEGER DEFAULT 0,
                roll_8 INTEGER DEFAULT 0,
                roll_9 INTEGER DEFAULT 0,
                roll_10 INTEGER DEFAULT 0,
                roll_11 INTEGER DEFAULT 0,
                roll_12 INTEGER DEFAULT 0,
                roll_13 INTEGER DEFAULT 0,
                roll_14 INTEGER DEFAULT 0,
                roll_15 INTEGER DEFAULT 0,
                roll_16 INTEGER DEFAULT 0,
                roll_17 INTEGER DEFAULT 0,
                roll_18 INTEGER DEFAULT 0,
                roll_19 INTEGER DEFAULT 0,
                roll_20 INTEGER DEFAULT 0
            )
        """)
        # Insert initial row with default values
        cursor.execute("INSERT INTO roll_results (id) VALUES (1) ON CONFLICT DO NOTHING")
        # Create last roll table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS last_roll (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                result INTEGER
            )
        """)
        # Create message objects table with is_roll column
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_objects (
                id INTEGER PRIMARY KEY,
                message_id INTEGER,
                channel_id INTEGER,
                is_roll BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()
        conn.close()

    def insert_roll_result(self, user_id, result):
        db_path = self.get_db_path(user_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE roll_results SET roll_{result} = roll_{result} + 1 WHERE id = 1")
        conn.commit()
        conn.close()

    def insert_last_roll(self, user_id, result):
        db_path = self.get_db_path(user_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Delete any existing rows in the last_roll table
        cursor.execute("DELETE FROM last_roll")
        # Insert the new row
        cursor.execute("INSERT INTO last_roll (timestamp, result) VALUES (?, ?)", (discord.utils.utcnow().isoformat(), result))
        conn.commit()
        conn.close()

    def get_last_roll_timestamp(self, user_id):
        db_path = self.get_db_path(user_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM last_roll")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    async def insert_or_update_message_object(self, user_id, message_id, channel_id, is_roll):
        db_path = self.get_db_path(user_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Check if a message object already exists
        cursor.execute("SELECT message_id, channel_id, is_roll FROM message_objects")
        row = cursor.fetchone()
        if row:
            existing_message_id, existing_channel_id, existing_is_roll = row
            # If the existing message is not a roll, delete it
            if not existing_is_roll:
                channel = self.bot.get_channel(existing_channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(existing_message_id)
                        await msg.delete()
                    except discord.NotFound:
                        pass
            # Update the message object
            cursor.execute("UPDATE message_objects SET message_id = ?, channel_id = ?, is_roll = ?", (message_id, channel_id, is_roll))
        else:
            # Insert a new message object
            cursor.execute("INSERT INTO message_objects (message_id, channel_id, is_roll) VALUES (?, ?, ?)", (message_id, channel_id, is_roll))
        conn.commit()
        conn.close()

    def get_message_object(self, user_id):
        db_path = self.get_db_path(user_id)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT message_id, channel_id, is_roll FROM message_objects")
        row = cursor.fetchone()
        conn.close()
        return row

    @commands.hybrid_command(name="d20", description="Rolls a d20.")
    async def d20(self, ctx: commands.Context):
        user_id = ctx.author.id

        # Create user database if it doesn't exist
        if not os.path.exists(self.get_db_path(user_id)):
            self.create_user_db(user_id)

        # Check the last roll timestamp
        last_roll_timestamp = self.get_last_roll_timestamp(user_id)
        if last_roll_timestamp:
            last_roll_time = datetime.datetime.fromisoformat(last_roll_timestamp)
            current_time = discord.utils.utcnow()
            if (current_time - last_roll_time).total_seconds() < cooldown_sec:
                retry_after = cooldown_sec - (current_time - last_roll_time).total_seconds()
                next_time = current_time + datetime.timedelta(seconds=retry_after)
                discord_timestamp = f"<t:{int(next_time.timestamp())}:R>"
                if isinstance(ctx.interaction, discord.Interaction):
                    message = await ctx.reply(f"You can only roll once every hour. Try again {discord_timestamp}.", ephemeral=True)
                else:
                    message = await ctx.reply(f"You can only roll once every hour. Try again {discord_timestamp}.")

                # Insert or update message object in the database
                await self.insert_or_update_message_object(user_id, message.id, message.channel.id, False)

                # Schedule the edit after the cooldown period
                await asyncio.sleep(retry_after)
                message_object = self.get_message_object(user_id)
                if message_object:
                    message_id, channel_id, is_roll = message_object
                    if is_roll == 0:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            try:
                                msg = await channel.fetch_message(message_id)
                                await msg.edit(content="You can roll again now!")
                            except discord.NotFound:
                                pass
                return

        # Generate a new roll
        rng = SystemRandom()
        result = rng.randint(1, 20)

        # Insert roll result
        self.insert_roll_result(user_id, result)

        # Insert last roll
        self.insert_last_roll(user_id, result)

        if result == 20:
            if isinstance(ctx.interaction, discord.Interaction):
                message = await ctx.reply(f':ccchaiYay: NAT `20`! :ccchaiYay:', ephemeral=True)
            else:
                message = await ctx.reply(f':ccchaiYay: NAT `20`! :ccchaiYay:')
        elif result == 1:
            if isinstance(ctx.interaction, discord.Interaction):
                message = await ctx.reply(f'oof, nat `1` :grimacing:', ephemeral=True)
            else:
                message = await ctx.reply(f'oof, nat `1` :grimacing:')
        else:
            if isinstance(ctx.interaction, discord.Interaction):
                message = await ctx.reply(f'You rolled: `{result}`', ephemeral=True)
            else:
                message = await ctx.reply(f'You rolled: `{result}`')

        # Insert or update message object in the database
        await self.insert_or_update_message_object(user_id, message.id, message.channel.id, True)

        # Schedule the edit after the cooldown period
        await asyncio.sleep(cooldown_sec)
        message_object = self.get_message_object(user_id)
        if message_object:
            message_id, channel_id, is_roll = message_object
            if is_roll == 0:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(content="You can roll again now!")
                    except discord.NotFound:
                        pass

    @commands.hybrid_command(name="d20stats", description="Displays statistics for your d20 rolls.")
    async def d20stats(self, ctx: commands.Context):
        user_id = ctx.author.id

        # Create user database if it doesn't exist
        if not os.path.exists(self.get_db_path(user_id)):
            if isinstance(ctx.interaction, discord.Interaction):
                await ctx.reply("You haven't used `$d20` yet. Please make your first roll before trying to look at your stats.", ephemeral=True)
            else:
                await ctx.reply("You haven't used `$d20` yet. Please make your first roll before trying to look at your stats.")
        else:
            db_path = self.get_db_path(user_id)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get the number of nat 20s
            cursor.execute("SELECT roll_20 FROM roll_results WHERE id = 1")
            nat_20s = cursor.fetchone()[0]

            # Get the number of nat 1s
            cursor.execute("SELECT roll_1 FROM roll_results WHERE id = 1")
            nat_1s = cursor.fetchone()[0]

            # Get the most rolled number(s)
            cursor.execute("SELECT roll_1, roll_2, roll_3, roll_4, roll_5, roll_6, roll_7, roll_8, roll_9, roll_10, roll_11, roll_12, roll_13, roll_14, roll_15, roll_16, roll_17, roll_18, roll_19, roll_20 FROM roll_results WHERE id = 1")
            roll_counts = cursor.fetchone()  # This is a tuple of roll counts (roll_1 to roll_20)
            max_count = max(roll_counts)
            most_rolled_numbers = [i + 1 for i, count in enumerate(roll_counts) if count == max_count]  # List of most rolled numbers

            # Format most rolled numbers
            if len(most_rolled_numbers) > 1:
                most_rolled_str = ", ".join(map(str, most_rolled_numbers))
                if max_count > 1:
                    most_rolled_label = f"Most rolled numbers [{max_count} rolls]"
                else:
                    most_rolled_label = f"Most rolled numbers [{max_count} roll]"
            else:
                most_rolled_str = str(most_rolled_numbers[0])
                if max_count > 1:
                    most_rolled_label = f"Most rolled number [{max_count} rolls]"
                else:
                    most_rolled_label = f"Most rolled number [{max_count} roll]"

            # Get the previous roll result
            cursor.execute("SELECT result FROM last_roll WHERE id = 1")
            last_roll = cursor.fetchone()
            previous_roll = last_roll[0] if last_roll else "None"

            conn.close()

            # Create the ASCII table
            table = texttable.Texttable()
            table.header(["Statistic", "Value"])
            table.add_row(["Number of nat 20s", nat_20s])
            table.add_row(["Number of nat 1s", nat_1s])
            table.add_row([most_rolled_label, most_rolled_str])
            table.add_row(["Previous roll result", previous_roll])

            # Send the table as a message
            if isinstance(ctx.interaction, discord.Interaction):
                await ctx.reply(f"```\n{table.draw()}\n```", ephemeral=True)
            else:
                await ctx.reply(f"```\n{table.draw()}\n```")
                

async def setup(bot):
    await bot.add_cog(D20(bot))
