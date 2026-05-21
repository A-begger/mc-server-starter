import discord
from discord.ext import commands
import os
from dotenv import load_dotenv


load_dotenv("secret.env")

TOKEN = os.getenv("bot_auth") or os.getenv("BOT_TOKEN")

if not TOKEN:
	raise RuntimeError("Missing Discord bot token in secret.env")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
	print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.command()
async def ping(ctx):
	await ctx.send(f"Pong! `{round(bot.latency * 1000)}ms`")


bot.run(TOKEN)

