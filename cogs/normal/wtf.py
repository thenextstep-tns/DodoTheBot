""""
Version 1.0
"""

import json
import os
import random
import sys
import asyncio
import inspirobot
import cat
import csv
import nekos
import numpy as np
import io
import sqlite3

import urllib.request
from urllib.request import urlopen

import re
import requests
import pymongo

import aiohttp
import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands
from disnake.ext.commands import Context

from helpers import checks
import PIL
from PIL import Image

if not os.path.isfile("config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open("config.json") as file:
        config = json.load(file)

if not os.path.isfile("config_py.py"):
    sys.exit("'config_py.py' not found! Please add it and try again.")
else:
    import config_py

connection = sqlite3.connect("dodo.db")
cursor = connection.cursor()

class Downloader(commands.Cog, name="downloader"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="downloadmessages",
        description="Get a random fact."
    )
    @checks.not_blacklisted()
    async def downloader(self, context: Context):
        """
        Get a random fact.
        """
        messages_collection = config_py.messages
        
        # Query to get all the documents and extract the "message" values
        messages_cursor = messages_collection.find({}, {'message': 1})
        
        # List to store all the "message" values
        message_list = [message_doc['message'] for message_doc in messages_cursor]
        
        # CSV file path to save the messages
        csv_file_path = 'messages.csv'
        
        # Write the messages to a CSV file
        with open(csv_file_path, 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(['Message'])
            csvwriter.writerows([[message] for message in message_list])
        
        print(f"Successfully extracted {len(message_list)} messages and saved to {csv_file_path}.")

#def setup(bot):
#    bot.add_cog(Downloader(bot))
