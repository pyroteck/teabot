import aiohttp
import json
from discord.ext import commands, tasks

class Stream(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.alreadyLive = True  # initially set to True so that any bot resets while stream is live doesn't send another message
        with open('secrets.json') as config_file:
            self.config = json.load(config_file)

    @tasks.loop(minutes=3)
    async def check_stream(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://api.twitch.tv/helix/streams?user_login={self.config["STREAMER_NAME"]}', headers={
                'Client-ID': self.config["TWITCH_CLIENT_ID"],
                'Authorization': f'Bearer {await self.get_access_token(session)}'
            }) as response:
                data = await response.json()
                if data['data'] and not self.alreadyLive:
                    channel = self.bot.get_channel(int(self.config["GOING_LIVE_CHANNEL_ID"]))
                    if channel:
                        await channel.send(f'{self.config["STREAMER_NAME"]} is now live! https://www.twitch.tv/{self.config["STREAMER_NAME"]} @everyone')
                        self.alreadyLive = True
                    else:
                        print(f"Channel with ID {self.config['GOING_LIVE_CHANNEL_ID']} not found.")
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
