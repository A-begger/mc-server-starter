import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import digitalocean as do

load_dotenv("secret.env")

TOKEN = os.getenv("bot_auth")
DO_TOKEN = os.getenv("DIGITALOCEAN_TOKEN")


intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        await self.tree.sync()


bot = MyBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
	print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.tree.command(name="ping", description="Check the bot latency", guild=discord.Object(id=480418557767843840))
async def ping_slash(interaction: discord.Interaction):
	await interaction.response.send_message(f"Pong! `{round(bot.latency * 1000)}ms`")

@bot.command() #testing my knowledge
async def balance(ctx):
    bal = do.get_balance()
    await ctx.send(f"Your DigitalOcean balance is: ${bal}")

@bot.command()
async def create(ctx):
    do.create_droplet()
    await ctx.send("Droplet created successfully!")

@bot.command()
async def destroy(ctx):
    drop_id = do.drop_id()
    do.destroy_droplet(drop_id)
    await ctx.send("Droplet destroyed successfully!")

@bot.tree.command(name="balance", description="Get your DigitalOcean balance")
async def balance_slash(interaction: discord.Interaction):
    bal = do.get_balance()
    await interaction.response.send_message(f"Your DigitalOcean balance is: ${bal}")

@bot.command()
async def start(ctx):
    await ctx.send("Starting server...")
    do.start()
    await ctx.send(f"Server started successfully! On {do.drop_ip()}")

@bot.command()
async def stop(ctx):
    await ctx.send("Stopping server...")
    do.stop()
    await ctx.send("Server stopped successfully!")

bot.run(TOKEN)

