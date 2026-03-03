import aiohttp
import datetime
import json
from discord.ext import commands, tasks
from discord import Embed

class Stream(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.alreadyLive = False
        with open('secrets.json') as config_file:
            self.config = json.load(config_file)

    @tasks.loop(minutes=3)
    async def check_stream(self):
        async with aiohttp.ClientSession() as session:
            # Get access token
            token = await self.get_access_token(session)

            # Get stream info
            async with session.get(f'https://api.twitch.tv/helix/streams?user_login={self.config["STREAMER_NAME"]}', headers={
                'Client-ID': self.config["TWITCH_CLIENT_ID"],
                'Authorization': f'Bearer {token}'
            }) as response:
                data = await response.json()

                if data['data'] and not self.alreadyLive:
                    # Get channel info for thumbnail
                    async with session.get(f'https://api.twitch.tv/helix/users?login={self.config["STREAMER_NAME"]}', headers={
                        'Client-ID': self.config["TWITCH_CLIENT_ID"],
                        'Authorization': f'Bearer {token}'
                    }) as user_response:
                        user_data = await user_response.json()
                        user_info = user_data['data'][0] if user_data['data'] else None

                        print(data['data'][0])

                        if user_info:
                            # Create embed
                            embed = Embed(
                                title=self.config["STREAMER_NAME"],
                                color=0x9146FF
                            )

                            # Add stream title and thumbnail
                            stream_info = data['data'][0]
                            embed.add_field(name="", value=f"[{stream_info['title']}](https://www.twitch.tv/{self.config["STREAMER_NAME"]})", inline=False)
                            embed.set_image(url=stream_info['thumbnail_url'].replace('{width}x{height}', '1920x1080'))
                            embed.set_thumbnail(url=user_info['profile_image_url'])
                            embed.timestamp = datetime.datetime.now()

                            channel = self.bot.get_channel(int(self.config["GOING_LIVE_CHANNEL_ID"]))
                            if channel:
                                await channel.send(f'{self.config["STREAMER_NAME"]} is now live! <https://www.twitch.tv/{self.config["STREAMER_NAME"]}> @everyone', embed=embed)
                                self.alreadyLive = True
                            else:
                                print(f"Channel with ID {self.config['GOING_LIVE_CHANNEL_ID']} not found.")
                        else:
                            print("Could not get user info")
                elif data['data'] and self.alreadyLive:
                    pass
                else:
                    self.alreadyLive = False

    async def get_access_token(self, session):
        async with session.post('https://id.twitch.tv/oauth2/token', params={
            'client_id': self.config["TWITCH_CLIENT_ID"],
            'client_secret': self.config["TWITCH_CLIENT_SECRET"],
            'grant_type': 'client_credentials'
        }) as response:
            data = await response.json()
            return data['access_token']


async def setup(bot):
    await bot.add_cog(Stream(bot))
