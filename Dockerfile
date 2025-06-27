FROM python:3.13.5-alpine3.22

RUN mkdir /data
VOLUME /data
WORKDIR /data

RUN pip install discord.py==2.5.2
RUN pip install aiohttp==3.11.14
RUN pip install texttable==1.7.0
RUN pip install pytz==2025.2
