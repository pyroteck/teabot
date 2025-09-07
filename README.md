# TeaBot

A Discord bot written in Python ([discord.py](https://discordpy.readthedocs.io/en/stable/)).

Created for use in [thechachachai's](https://www.twitch.tv/thechachachai) Discord channel, but designed with the intention to be used by anyone. 

&nbsp;

## Initial Setup

Clone the repository to a directory of your choice

Create a file in the source directory named `secrets.json` with the following:

```json
{
    "CLIENT_TOKEN": "",
    "TWITCH_CLIENT_ID": "",
    "TWITCH_CLIENT_SECRET": "",
    "STREAMER_NAME": "",
    "GOING_LIVE_CHANNEL_ID": "",
    "NEW_USER_JOIN_ROLE_ID": "",
    "LOGS_CHANNEL_ID": "",
    "TIMEZONE": ""
}
```
Add the following data in the quotes:
```
CLIENT_TOKEN:           Your Discord bot application's token
TWITCH_CLIENT_ID:       Twitch client ID token
TWITCH_CLIENT_SECRET:   Twitch client secret token
STREAMER_NAME:          Twitch streamer's name to check for going live
GOING_LIVE_CHANNEL_ID:  Channel ID to send a message to @everyone when the bot detects the streamer going live.
NEW_USER_JOIN_ROLE_ID:  Role ID to automatically assign to new users
LOGS_CHANNEL_ID:        Channel ID for the bot to send moderation logs to.
TIMEZONE:               Timezone for your bot to refer to
```

For a full list of valid timezones, refer to [this list](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568).

&nbsp;

## Running with Docker

Navigate to root directory of the repository.

Run
```
sudo docker compose up -d
```
to build and run the Docker container.

&nbsp;

## Running Locally

Install [python 3.13.x](https://www.python.org/downloads/)

Install necessary pip packages

```
pip install discord.py
```
```
pip install aiohttp
```
```
pip install texttable
```
```
pip install pytz
```

Once all the packages are installed, navigate to `./data` and run the `bot.py` file

```
python bot.py
```

&nbsp;

### Packages and versions used during development

* Python
    * 3.13.2
* discord.py
    * 2.5.2
* aiohttp
    * 3.11.14
* texttable
    * 1.7.0
* pytz
    * 2025.2

