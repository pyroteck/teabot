import aiohttp
import datetime
import json
import os
from discord.ext import commands, tasks
from discord import Embed, File

class Stream(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.alreadyLive = True # initially set to True so that messasge doesn't get sent on bot startup if already live
        self.stream_message = None
        self.stream_start_time = None
        self.thumbnail_path = "twitch_thumbnail.png"
        with open('secrets.json') as config_file:
            self.config = json.load(config_file)

    @tasks.loop(minutes=3)
    async def check_stream(self):
        async with aiohttp.ClientSession() as session:
            # Get access token
            token = await self.get_access_token(session)

            # Get stream info to check if live
            async with session.get(f'https://api.twitch.tv/helix/streams?user_login={self.config["STREAMER_NAME"]}', headers={
                'Client-ID': self.config["TWITCH_CLIENT_ID"],
                'Authorization': f'Bearer {token}'
            }) as response:
                data = await response.json()

                if data['data'] and not self.alreadyLive:
                    async with session.get(f'https://api.twitch.tv/helix/users?login={self.config["STREAMER_NAME"]}', headers={
                        'Client-ID': self.config["TWITCH_CLIENT_ID"],
                        'Authorization': f'Bearer {token}'
                    }) as user_response:
                        user_data = await user_response.json()
                        user_info = user_data['data'][0] if user_data['data'] else None

                        if user_info:
                            # Download thumbnail first
                            thumbnail_url = data['data'][0]['thumbnail_url'].replace('{width}x{height}', '1920x1080')
                            await self.download_thumbnail(thumbnail_url)

                            stream_info = data['data'][0]

                            embed = Embed(
                                title=stream_info['title'],
                                color=0x9146FF
                            )

                            embed.add_field(
                                name="",
                                value=f"""
                                [{stream_info['user_name']}](https://www.twitch.tv/{stream_info['user_login']})
                                {stream_info['game_name']}
                                """,
                                inline=False
                            )

                            # Set thumbnail from file attachment
                            if os.path.exists(self.thumbnail_path):
                                file = File(self.thumbnail_path, filename="twitch_thumbnail.png")
                                embed.set_image(url="attachment://twitch_thumbnail.png")
                                embed.set_thumbnail(url=user_info['profile_image_url'])

                                self.stream_start_time = datetime.datetime.now()
                                embed.timestamp = self.stream_start_time

                                channel = self.bot.get_channel(int(self.config["GOING_LIVE_CHANNEL_ID"]))
                                if channel:
                                    self.stream_message = await channel.send(f'{self.config["STREAMER_NAME"]} is now live! <https://www.twitch.tv/{self.config["STREAMER_NAME"]}> @everyone', embed=embed, file=file)
                                    self.alreadyLive = True
                                else:
                                    print(f"Channel with ID {self.config['GOING_LIVE_CHANNEL_ID']} not found.")
                        else:
                            print("Could not get user info")
                elif data['data'] and self.alreadyLive:
                    # if stream is already live, do not send message and do not set variables false/none
                    pass
                else:
                    self.alreadyLive = False
                    self.stream_message = None
                    # Clean up thumbnail file
                    if os.path.exists(self.thumbnail_path):
                        os.remove(self.thumbnail_path)

    # When stream is live, update thumbnail every 6 minutes since Twitch updates the thumbnail every 5
    @tasks.loop(minutes=6)
    async def update_thumbnail(self):
        if self.alreadyLive and self.stream_message:
            async with aiohttp.ClientSession() as session:
                token = await self.get_access_token(session)

                # Get stream info to check if live
                async with session.get(f'https://api.twitch.tv/helix/streams?user_login={self.config["STREAMER_NAME"]}', headers={
                    'Client-ID': self.config["TWITCH_CLIENT_ID"],
                    'Authorization': f'Bearer {token}'
                }) as response:
                    data = await response.json()

                    if data['data']:
                        stream_info = data['data'][0]

                        async with session.get(f'https://api.twitch.tv/helix/users?login={self.config["STREAMER_NAME"]}', headers={
                            'Client-ID': self.config["TWITCH_CLIENT_ID"],
                            'Authorization': f'Bearer {token}'
                        }) as user_response:
                            user_data = await user_response.json()
                            user_info = user_data['data'][0] if user_data['data'] else None

                            if user_info:
                                # Download new thumbnail
                                thumbnail_url = stream_info['thumbnail_url'].replace('{width}x{height}', '1920x1080')
                                await self.download_thumbnail(thumbnail_url)

                                # Update embed with new metadata
                                embed = Embed(
                                    title=stream_info['title'],
                                    color=0x9146FF
                                )

                                embed.add_field(
                                    name="",
                                    value=f"""
                                    [{stream_info['user_name']}](https://www.twitch.tv/{stream_info['user_login']})
                                    {stream_info['game_name']}
                                    """,
                                    inline=False
                                )

                                # Grab newly downloaded thumbnail and update the embed
                                if os.path.exists(self.thumbnail_path):
                                    file = File(self.thumbnail_path, filename="twitch_thumbnail.png")
                                    embed.set_image(url="attachment://twitch_thumbnail.png")
                                    embed.set_thumbnail(url=user_info['profile_image_url'])
                                    embed.timestamp = self.stream_start_time

                                    try:
                                        await self.stream_message.edit(embed=embed, attachments=[file])
                                    except Exception as e:
                                        print("There was an error updating the stream message with new metadata.")
                                        print(f"{e}")
                    else:
                        # Stream ended, stop updating
                        self.alreadyLive = False
                        self.stream_message = None

    async def download_thumbnail(self, url):
        """Download thumbnail from URL and save it locally since direct link doesn't always update immediately on Discord"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(self.thumbnail_path, 'wb') as f:
                            f.write(await response.read())
        except Exception as e:
            print(f"Error downloading thumbnail: {e}")

    async def get_access_token(self, session):
        async with session.post('https://id.twitch.tv/oauth2/token', params={
            'client_id': self.config["TWITCH_CLIENT_ID"],
            'client_secret': self.config["TWITCH_CLIENT_SECRET"],
            'grant_type': 'client_credentials'
        }) as response:
            data = await response.json()
            return data['access_token']

    async def cog_load(self):
        self.check_stream.start()
        self.update_thumbnail.start()

async def setup(bot):
    await bot.add_cog(Stream(bot))
