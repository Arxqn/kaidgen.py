import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import json
import os
import asyncio
import threading
import string
import requests
import base64
import traceback
import re
from datetime import datetime

# Flask web server for Render port binding
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

threading.Thread(target=run_web, daemon=True).start()

# PINGER TO KEEP BOT AWAKE
def keep_alive():
    web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://your-bot.onrender.com")
    while True:
        try:
            response = requests.get(f"{web_url}/health", timeout=10)
            if response.status_code == 200:
                print(f"[KEEP-ALIVE] Ping sent at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        except:
            pass
        time.sleep(840)

if os.environ.get("RENDER"):
    threading.Thread(target=keep_alive, daemon=True).start()
    print("[PINGER] Auto-pinger started")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.invites = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================
# GITHUB STORAGE SYSTEM (PERSISTENT)
# ============================================

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "YOUR_USERNAME/YOUR_REPO_NAME")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

def github_api_request(endpoint, method="GET", data=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    if data:
        headers["Content-Type"] = "application/json"
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "PUT":
        response = requests.put(url, headers=headers, json=data)
    
    return response

def load_from_github(filename):
    if not GITHUB_TOKEN:
        return None
    try:
        response = github_api_request(f"contents/{filename}")
        if response.status_code == 200:
            content = base64.b64decode(response.json()["content"]).decode()
            return json.loads(content)
        return None
    except:
        return None

def save_to_github(filename, data, commit_message="Update data"):
    if not GITHUB_TOKEN:
        return False
    try:
        response = github_api_request(f"contents/{filename}")
        sha = response.json().get("sha") if response.status_code == 200 else None
        
        content_str = json.dumps(data, indent=4)
        encoded_content = base64.b64encode(content_str.encode()).decode()
        
        commit_data = {
            "message": commit_message,
            "content": encoded_content,
            "branch": GITHUB_BRANCH
        }
        if sha:
            commit_data["sha"] = sha
        
        response = github_api_request(f"contents/{filename}", "PUT", commit_data)
        return response.status_code in [200, 201]
    except:
        return False

# ============================================
# PER-SERVER STORAGE
# ============================================

# Store all data per server
server_free_stock = {}
server_prem_stock = {}
server_free_channels = {}
server_prem_channels = {}
server_invite_data = {}
server_active_keys = {}
server_redeemed_users = {}
server_bot_config = {}
server_free_cooldowns = {}
server_prem_cooldowns = {}

# Default config
DEFAULT_CONFIG = {
    "free_gen_role_name": "free gen",
    "prem_gen_role_name": "prem gen",
    "free_role_invites_required": 1,
    "invite_reward_count": 5,
    "invite_age_required_days": 7,
    "invite_reward_duration": "24",
    "default_free_cooldown": 30,
    "default_prem_cooldown": 30
}

# ============================================
# PER-SERVER FILE FUNCTIONS
# ============================================

def get_server_stock_file(guild_id):
    return f"stock_data_{guild_id}.json"

def get_server_channels_file(guild_id):
    return f"channels_{guild_id}.json"

def get_server_invites_file(guild_id):
    return f"invites_{guild_id}.json"

def get_server_keys_file(guild_id):
    return f"keys_{guild_id}.json"

def get_server_config_file(guild_id):
    return f"config_{guild_id}.json"

def load_server_data(guild_id):
    """Load all data for a specific server"""
    guild_id_str = str(guild_id)
    
    # Load stock
    stock_file = get_server_stock_file(guild_id_str)
    if os.path.exists(stock_file):
        with open(stock_file, "r") as f:
            data = json.load(f)
            server_free_stock[guild_id_str] = data.get("free_stock", [])
            server_prem_stock[guild_id_str] = data.get("prem_stock", [])
    else:
        data = load_from_github(stock_file)
        if data:
            server_free_stock[guild_id_str] = data.get("free_stock", [])
            server_prem_stock[guild_id_str] = data.get("prem_stock", [])
            save_server_stock(guild_id_str)
        else:
            server_free_stock[guild_id_str] = []
            server_prem_stock[guild_id_str] = []
    print(f"[LOAD] Server {guild_id} Stock: {len(server_free_stock[guild_id_str])} free, {len(server_prem_stock[guild_id_str])} prem")
    
    # Load channels
    channels_file = get_server_channels_file(guild_id_str)
    if os.path.exists(channels_file):
        with open(channels_file, "r") as f:
            data = json.load(f)
            server_free_channels[guild_id_str] = data.get("free_channels", [])
            server_prem_channels[guild_id_str] = data.get("prem_channels", [])
    else:
        server_free_channels[guild_id_str] = []
        server_prem_channels[guild_id_str] = []
    
    # Load invites
    invites_file = get_server_invites_file(guild_id_str)
    if os.path.exists(invites_file):
        with open(invites_file, "r") as f:
            server_invite_data[guild_id_str] = json.load(f)
    else:
        server_invite_data[guild_id_str] = {}
    
    # Load keys
    keys_file = get_server_keys_file(guild_id_str)
    if os.path.exists(keys_file):
        with open(keys_file, "r") as f:
            data = json.load(f)
            server_active_keys[guild_id_str] = data.get("active_keys", {})
            server_redeemed_users[guild_id_str] = data.get("redeemed_users", {})
    else:
        server_active_keys[guild_id_str] = {}
        server_redeemed_users[guild_id_str] = {}
    
    # Load config
    config_file = get_server_config_file(guild_id_str)
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            server_bot_config[guild_id_str] = json.load(f)
    else:
        server_bot_config[guild_id_str] = DEFAULT_CONFIG.copy()
    
    # Initialize cooldown dicts
    if guild_id_str not in server_free_cooldowns:
        server_free_cooldowns[guild_id_str] = {}
    if guild_id_str not in server_prem_cooldowns:
        server_prem_cooldowns[guild_id_str] = {}

def save_server_stock(guild_id, send_backup=False):
    """Save stock for a specific server - backup only sent if send_backup=True"""
    guild_id_str = str(guild_id)
    stock_file = get_server_stock_file(guild_id_str)
    data = {"free_stock": server_free_stock.get(guild_id_str, []), "prem_stock": server_prem_stock.get(guild_id_str, [])}
    with open(stock_file, "w") as f:
        json.dump(data, f, indent=4)
    save_to_github(stock_file, data, f"Stock updated for server {guild_id}")
    
    # Only send backup if explicitly requested
    if send_backup:
        asyncio.create_task(send_stock_file_to_owner(guild_id_str))

def save_server_channels(guild_id):
    guild_id_str = str(guild_id)
    channels_file = get_server_channels_file(guild_id_str)
    data = {"free_channels": server_free_channels.get(guild_id_str, []), "prem_channels": server_prem_channels.get(guild_id_str, [])}
    with open(channels_file, "w") as f:
        json.dump(data, f, indent=4)

def save_server_invites(guild_id):
    guild_id_str = str(guild_id)
    invites_file = get_server_invites_file(guild_id_str)
    with open(invites_file, "w") as f:
        json.dump(server_invite_data.get(guild_id_str, {}), f, indent=4)

def save_server_keys(guild_id):
    guild_id_str = str(guild_id)
    keys_file = get_server_keys_file(guild_id_str)
    data = {"active_keys": server_active_keys.get(guild_id_str, {}), "redeemed_users": server_redeemed_users.get(guild_id_str, {})}
    with open(keys_file, "w") as f:
        json.dump(data, f, indent=4)

def save_server_config(guild_id):
    guild_id_str = str(guild_id)
    config_file = get_server_config_file(guild_id_str)
    with open(config_file, "w") as f:
        json.dump(server_bot_config.get(guild_id_str, DEFAULT_CONFIG), f, indent=4)

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_server_free_stock(guild_id):
    guild_id_str = str(guild_id)
    return server_free_stock.get(guild_id_str, [])

def get_server_prem_stock(guild_id):
    guild_id_str = str(guild_id)
    return server_prem_stock.get(guild_id_str, [])

def get_server_free_channels(guild_id):
    guild_id_str = str(guild_id)
    return server_free_channels.get(guild_id_str, [])

def get_server_prem_channels(guild_id):
    guild_id_str = str(guild_id)
    return server_prem_channels.get(guild_id_str, [])

def get_server_config(guild_id):
    guild_id_str = str(guild_id)
    return server_bot_config.get(guild_id_str, DEFAULT_CONFIG)

def get_server_invite_data(guild_id):
    guild_id_str = str(guild_id)
    return server_invite_data.get(guild_id_str, {})

def get_server_active_keys(guild_id):
    guild_id_str = str(guild_id)
    return server_active_keys.get(guild_id_str, {})

def get_server_redeemed_users(guild_id):
    guild_id_str = str(guild_id)
    return server_redeemed_users.get(guild_id_str, {})

def check_free_cooldown(guild_id, user_id):
    guild_id_str = str(guild_id)
    config = get_server_config(guild_id)
    default_cooldown = config.get("default_free_cooldown", 30)
    cooldowns = server_free_cooldowns.get(guild_id_str, {})
    if user_id in cooldowns:
        elapsed = time.time() - cooldowns[user_id]
        if elapsed < default_cooldown:
            return False, round(default_cooldown - elapsed)
    return True, 0

def set_free_cooldown(guild_id, user_id):
    guild_id_str = str(guild_id)
    if guild_id_str not in server_free_cooldowns:
        server_free_cooldowns[guild_id_str] = {}
    server_free_cooldowns[guild_id_str][user_id] = time.time()

def check_prem_cooldown(guild_id, user_id):
    guild_id_str = str(guild_id)
    config = get_server_config(guild_id)
    default_cooldown = config.get("default_prem_cooldown", 30)
    cooldowns = server_prem_cooldowns.get(guild_id_str, {})
    if user_id in cooldowns:
        elapsed = time.time() - cooldowns[user_id]
        if elapsed < default_cooldown:
            return False, round(default_cooldown - elapsed)
    return True, 0

def set_prem_cooldown(guild_id, user_id):
    guild_id_str = str(guild_id)
    if guild_id_str not in server_prem_cooldowns:
        server_prem_cooldowns[guild_id_str] = {}
    server_prem_cooldowns[guild_id_str][user_id] = time.time()

async def send_stock_file_to_owner(guild_id):
    """Send the actual stock JSON file to owner's DMs"""
    try:
        OWNER_USER_ID = 1065039387433381898
        owner = None
        for guild in bot.guilds:
            owner = guild.get_member(OWNER_USER_ID)
            if owner:
                break
        
        if not owner:
            print(f"[BACKUP] Owner not found")
            return
        
        stock_file = get_server_stock_file(guild_id)
        if os.path.exists(stock_file):
            with open(stock_file, "rb") as f:
                file = discord.File(f, filename=f"stock_backup_{guild_id}_{int(time.time())}.json")
                
                free_count = len(get_server_free_stock(guild_id))
                prem_count = len(get_server_prem_stock(guild_id))
                
                embed = discord.Embed(
                    title="📦 Stock Backup File",
                    description=f"**Server ID:** `{guild_id}`\n"
                                f"**Time:** <t:{int(time.time())}:F>\n\n"
                                f"• Free Stock: `{free_count}` lines\n"
                                f"• Premium Stock: `{prem_count}` lines\n\n"
                                f"**📁 The stock file is attached below**",
                    color=discord.Color.dark_gray()
                )
                embed.set_footer(text="made by Arxqn")
                await owner.send(embed=embed, file=file)
                print(f"[BACKUP] ✅ Sent stock file for server {guild_id}")
        else:
            print(f"[BACKUP] Stock file not found: {stock_file}")
    except Exception as e:
        print(f"[BACKUP] Error: {e}")

def generate_key():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(16))

def get_expiry_timestamp(hours):
    """Convert hours to expiry timestamp"""
    return time.time() + (hours * 60 * 60)

def format_time_left(expiry):
    remaining = expiry - time.time()
    if remaining <= 0:
        return "Expired"
    days = int(remaining // 86400)
    hours = int((remaining % 86400) // 3600)
    if days > 0:
        return f"{days}d {hours}h"
    else:
        return f"{hours}h"

async def check_invite_age(member):
    guild_id = str(member.guild.id)
    config = get_server_config(guild_id)
    age_days = config.get("invite_age_required_days", 7)
    account_age = time.time() - member.created_at.timestamp()
    return account_age >= (age_days * 24 * 60 * 60)

def create_premium_key_for_user(guild_id, hours, user_id):
    key = generate_key()
    expiry = get_expiry_timestamp(hours)
    guild_keys = get_server_active_keys(guild_id)
    guild_keys[key] = {
        "expiry": expiry,
        "created_by": "system",
        "created_at": time.time(),
        "duration_hours": hours,
        "used": False,
        "intended_user": user_id,
        "is_reward": True
    }
    server_active_keys[str(guild_id)] = guild_keys
    save_server_keys(guild_id)
    return key

def is_admin(interaction):
    return interaction.user.guild_permissions.administrator

def get_bot_avatar():
    return bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url

# ============================================
# COPY BUTTON VIEW
# ============================================

class CopyButton(discord.ui.View):
    def __init__(self, credentials):
        super().__init__(timeout=120)
        self.credentials = credentials
    
    @discord.ui.button(label="📋 Copy Credentials", style=discord.ButtonStyle.secondary, emoji="📋")
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"```\n{self.credentials}\n```", ephemeral=True)
        await interaction.followup.send("✅ Credentials copied!", ephemeral=True)

# ============================================
# ON READY
# ============================================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    for guild in bot.guilds:
        load_server_data(guild.id)
        setattr(bot, f"invite_cache_{guild.id}", await guild.invites())
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(e)
    
    bot.loop.create_task(check_expired_premium())
    print(f"[READY] All data loaded for {len(bot.guilds)} servers!")

# ============================================
# INVITE SYSTEM
# ============================================

@bot.event
async def on_member_join(member):
    guild = member.guild
    guild_id = str(guild.id)
    await bot.wait_until_ready()
    await asyncio.sleep(2)
    
    new_invites = await guild.invites()
    old_invites = getattr(bot, f"invite_cache_{guild_id}", [])
    
    for invite in new_invites:
        old_invite = discord.utils.get(old_invites, code=invite.code)
        if old_invite and invite.uses > old_invite.uses:
            inviter = invite.inviter
            if inviter:
                if not await check_invite_age(member):
                    break
                
                inviter_id = str(inviter.id)
                invite_data = get_server_invite_data(guild_id)
                invite_data[inviter_id] = invite_data.get(inviter_id, 0) + 1
                server_invite_data[guild_id] = invite_data
                save_server_invites(guild_id)
                
                config = get_server_config(guild_id)
                
                # Check for free gen role
                free_role_invites = config.get("free_role_invites_required", 1)
                role_name = config.get("free_gen_role_name", "free gen")
                role = discord.utils.get(guild.roles, name=role_name)
                if role and invite_data[inviter_id] >= free_role_invites:
                    member_to_role = guild.get_member(int(inviter_id))
                    if member_to_role and role not in member_to_role.roles:
                        await member_to_role.add_roles(role)
                        print(f"[INVITE] Gave {role_name} role to {member_to_role.name} for {invite_data[inviter_id]} invites")
                
                # Check for premium key reward
                reward_count = config.get("invite_reward_count", 5)
                if invite_data[inviter_id] >= reward_count:
                    if not invite_data.get(f"{inviter_id}_rewarded", False):
                        reward_hours = int(config.get("invite_reward_duration", "24"))
                        key = create_premium_key_for_user(guild_id, reward_hours, inviter.id)
                        invite_data[f"{inviter_id}_rewarded"] = True
                        server_invite_data[guild_id] = invite_data
                        save_server_invites(guild_id)
                        try:
                            dm_embed = discord.Embed(
                                title=f"🎉 You reached {reward_count} invites!",
                                description=f"**Reward:** {reward_hours}-Hour Premium Key\n**Key:** `{key}`\nUse `/redeemkey {key}`",
                                color=discord.Color.dark_gray()
                            )
                            dm_embed.set_footer(text="made by Arxqn")
                            await inviter.send(embed=dm_embed)
                            print(f"[INVITE] Sent premium key to {inviter.name} for {reward_count} invites")
                        except:
                            pass
                break
    
    setattr(bot, f"invite_cache_{guild_id}", new_invites)

async def check_expired_premium():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                guild_id = str(guild.id)
                config = get_server_config(guild_id)
                role_name = config.get("prem_gen_role_name", "prem gen")
                prem_role = discord.utils.get(guild.roles, name=role_name)
                redeemed = get_server_redeemed_users(guild_id)
                
                if prem_role:
                    to_remove = []
                    for user_id_str, expiry in list(redeemed.items()):
                        if time.time() > expiry:
                            to_remove.append(int(user_id_str))
                    for user_id in to_remove:
                        member = guild.get_member(user_id)
                        if member and prem_role in member.roles:
                            await member.remove_roles(prem_role)
                            del redeemed[str(user_id)]
                    if to_remove:
                        server_redeemed_users[guild_id] = redeemed
                        save_server_keys(guild_id)
            await asyncio.sleep(3600)
        except:
            await asyncio.sleep(3600)

# ============================================
# SETUP COMMAND
# ============================================

@bot.tree.command(name="setup", description="[ADMIN] Auto-setup Gen category with all features")
async def setup(interaction: discord.Interaction, ticket_channel: discord.TextChannel):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild = interaction.guild
    guild_id = str(guild.id)
    config = get_server_config(guild_id)
    
    free_role = discord.utils.get(guild.roles, name="free gen") or await guild.create_role(name="free gen", color=discord.Color.dark_gray())
    prem_role = discord.utils.get(guild.roles, name="prem gen") or await guild.create_role(name="prem gen", color=discord.Color.dark_gray())
    
    cat = await guild.create_category("Gen")
    free_ch = await guild.create_text_channel("free", category=cat)
    prem_ch = await guild.create_text_channel("prem", category=cat)
    
    for ch in [free_ch, prem_ch]:
        await ch.set_permissions(guild.default_role, send_messages=False)
        await ch.set_permissions(interaction.user, send_messages=True, read_messages=True)
    
    # Save channels
    free_channels = get_server_free_channels(guild_id)
    prem_channels = get_server_prem_channels(guild_id)
    if free_ch.id not in free_channels:
        free_channels.append(free_ch.id)
    if prem_ch.id not in prem_channels:
        prem_channels.append(prem_ch.id)
    server_free_channels[guild_id] = free_channels
    server_prem_channels[guild_id] = prem_channels
    save_server_channels(guild_id)
    
    free_role_invites = config.get("free_role_invites_required", 1)
    reward_count = config.get("invite_reward_count", 5)
    reward_hours = config.get("invite_reward_duration", "24")
    age_days = config.get("invite_age_required_days", 7)
    
    confirm = discord.Embed(title="✅ Setup Complete", color=discord.Color.dark_gray())
    confirm.add_field(name="Created", value=f"Category: **Gen**\n{free_ch.mention} - Free gen channel\n{prem_ch.mention} - Premium gen channel", inline=False)
    confirm.add_field(name="Roles Created", value=f"{free_role.mention}\n{prem_role.mention}", inline=False)
    confirm.add_field(name="ℹ️ Commands", value="• `/gen free/prem` - Generate accounts\n• `/stockcount` - Check stock\n• `/redeemkey` - Activate premium keys\n• `/getinvite` - Get invite link\n• `/checkinvites` - Claim free gen role and check progress\n• `/config` - Open config menu", inline=False)
    confirm.set_footer(text="made by Arxqn")
    await interaction.followup.send(embed=confirm, ephemeral=True)

# ============================================
# AUDIT COMMANDS
# ============================================

@bot.tree.command(name="auditprem", description="[ADMIN] Check premium status of a user")
async def audit_prem(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    uid = str(user.id)
    redeemed = get_server_redeemed_users(guild_id)
    
    embed = discord.Embed(title=f"🔍 Premium Audit - {user.name}", color=discord.Color.dark_gray())
    
    if uid in redeemed:
        expiry = redeemed[uid]
        if time.time() > expiry:
            embed.add_field(name="Premium Status", value="❌ Expired", inline=True)
        else:
            embed.add_field(name="Premium Status", value="✅ Active", inline=True)
            embed.add_field(name="Expires", value=f"<t:{int(expiry)}:R>\n{format_time_left(expiry)}", inline=True)
    else:
        embed.add_field(name="Premium Status", value="❌ No premium time", inline=True)
    
    embed.set_footer(text="made by Arxqn")
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="auditstock", description="[ADMIN] Check main stock count")
async def audit_stock(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    free = get_server_free_stock(guild_id)
    prem = get_server_prem_stock(guild_id)
    
    embed = discord.Embed(title="📊 Main Stock Audit", color=discord.Color.dark_gray())
    embed.add_field(name="Free Stock", value=f"{len(free)} lines", inline=True)
    embed.add_field(name="Premium Stock", value=f"{len(prem)} lines", inline=True)
    embed.set_footer(text="made by Arxqn")
    await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# STOCK MANAGEMENT COMMANDS
# ============================================

@bot.tree.command(name="addstock", description="[ADMIN] Add lines to stock")
@app_commands.describe(stock_type="free or prem", lines="Paste multiple lines, each on new line")
async def addstock(interaction: discord.Interaction, stock_type: str, lines: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    
    line_list = [l.strip() for l in lines.split('\n') if l.strip()]
    if not line_list:
        await interaction.followup.send("❌ No valid lines", ephemeral=True)
        return
    added = 0
    
    free_stock = get_server_free_stock(guild_id)
    prem_stock = get_server_prem_stock(guild_id)
    
    if stock_type.lower() == "free":
        for l in line_list:
            free_stock.append(l)
            added += 1
        server_free_stock[guild_id] = free_stock
        save_server_stock(guild_id, send_backup=True)
        await interaction.followup.send(f"✅ Added {added} lines to free stock. Total: {len(free_stock)}", ephemeral=True)
    elif stock_type.lower() == "prem":
        for l in line_list:
            prem_stock.append(l)
            added += 1
        server_prem_stock[guild_id] = prem_stock
        save_server_stock(guild_id, send_backup=True)
        await interaction.followup.send(f"✅ Added {added} lines to premium stock. Total: {len(prem_stock)}", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `free` or `prem`", ephemeral=True)

@bot.tree.command(name="addstockfile", description="[ADMIN] Upload a .txt file to add many lines")
@app_commands.describe(stock_type="free or prem", file="Text file with one line per entry")
async def addstockfile(interaction: discord.Interaction, stock_type: str, file: discord.Attachment):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    
    if not file.filename.endswith('.txt'):
        await interaction.followup.send("❌ Please upload a `.txt` file.", ephemeral=True)
        return
    
    try:
        content = await file.read()
        text = content.decode('utf-8')
        line_list = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not line_list:
            await interaction.followup.send("❌ File is empty.", ephemeral=True)
            return
        
        added = 0
        
        free_stock = get_server_free_stock(guild_id)
        prem_stock = get_server_prem_stock(guild_id)
        
        if stock_type.lower() == "free":
            for line in line_list:
                free_stock.append(line)
                added += 1
            server_free_stock[guild_id] = free_stock
            save_server_stock(guild_id, send_backup=True)
            await interaction.followup.send(f"✅ Added **{added}** lines from file to free stock. Total: `{len(free_stock)}`", ephemeral=True)
        elif stock_type.lower() == "prem":
            for line in line_list:
                prem_stock.append(line)
                added += 1
            server_prem_stock[guild_id] = prem_stock
            save_server_stock(guild_id, send_backup=True)
            await interaction.followup.send(f"✅ Added **{added}** lines from file to premium stock. Total: `{len(prem_stock)}`", ephemeral=True)
        else:
            await interaction.followup.send("❌ Invalid stock type. Use `free` or `prem`.", ephemeral=True)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="clearstock", description="[ADMIN] Clear stock")
async def clearstock(interaction: discord.Interaction, stock_type: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    
    if stock_type.lower() == "free":
        server_free_stock[guild_id] = []
        save_server_stock(guild_id, send_backup=True)
        await interaction.followup.send("✅ Free stock cleared", ephemeral=True)
    elif stock_type.lower() == "prem":
        server_prem_stock[guild_id] = []
        save_server_stock(guild_id, send_backup=True)
        await interaction.followup.send("✅ Premium stock cleared", ephemeral=True)
    elif stock_type.lower() == "both":
        server_free_stock[guild_id] = []
        server_prem_stock[guild_id] = []
        save_server_stock(guild_id, send_backup=True)
        await interaction.followup.send("✅ Both stocks cleared", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `free`, `prem`, or `both`", ephemeral=True)

@bot.tree.command(name="stockcount", description="Check stock count")
async def stockcount(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    free_stock = get_server_free_stock(guild_id)
    prem_stock = get_server_prem_stock(guild_id)
    
    embed = discord.Embed(title="📊 Stock Count", color=discord.Color.dark_gray())
    embed.add_field(name="Free Stock", value=f"`{len(free_stock)}` lines", inline=True)
    embed.add_field(name="Premium Stock", value=f"`{len(prem_stock)}` lines", inline=True)
    embed.set_footer(text="made by Arxqn", icon_url=get_bot_avatar())
    await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# CREATEKEY COMMAND
# ============================================

@bot.tree.command(name="createkey", description="[ADMIN] Create premium key for user (custom hours)")
@app_commands.describe(hours="Duration in hours (e.g., 24, 48, 72, 168)", user="The user who will receive the key")
async def createkey(interaction: discord.Interaction, hours: int, user: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    if hours < 1:
        await interaction.followup.send("❌ Hours must be at least 1.", ephemeral=True)
        return
    
    if hours > 8760:
        await interaction.followup.send("❌ Hours cannot exceed 8760 (1 year).", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    key = generate_key()
    expiry = get_expiry_timestamp(hours)
    active_keys = get_server_active_keys(guild_id)
    active_keys[key] = {
        "expiry": expiry,
        "created_by": interaction.user.id,
        "created_at": time.time(),
        "duration_hours": hours,
        "used": False,
        "intended_user": user.id
    }
    server_active_keys[guild_id] = active_keys
    save_server_keys(guild_id)
    
    if hours >= 24:
        days = hours // 24
        remainder_hours = hours % 24
        if remainder_hours > 0:
            duration_display = f"{days}d {remainder_hours}h"
        else:
            duration_display = f"{days}d"
    else:
        duration_display = f"{hours}h"
    
    try:
        dm_embed = discord.Embed(
            title="🔑 Your Premium Key",
            description=f"**Key:** `{key}`\n**Duration:** {duration_display} ({hours} hours)\nUse `/redeemkey {key}`",
            color=discord.Color.dark_gray()
        )
        dm_embed.set_footer(text="made by Arxqn")
        await user.send(embed=dm_embed)
        await interaction.followup.send(f"✅ {duration_display} key sent to {user.mention}", ephemeral=True)
    except:
        await interaction.followup.send(f"❌ Could not DM {user.mention}", ephemeral=True)

# ============================================
# GEN COMMAND
# ============================================

@bot.tree.command(name="gen", description="Generate free or premium account")
async def gen(interaction: discord.Interaction, stock_type: str):
    if interaction.guild is None:
        await interaction.response.send_message("❌ This command can only be used in a server, not in DMs.", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    
    if stock_type.lower() == "free":
        free_channels = get_server_free_channels(guild_id)
        if interaction.channel.id not in free_channels:
            await interaction.response.send_message("❌ Use in #free channel.", ephemeral=True)
            return
        
        config = get_server_config(guild_id)
        role_name = config.get("free_gen_role_name", "free gen")
        role = discord.utils.get(interaction.user.roles, name=role_name)
        if not role and not is_admin(interaction):
            await interaction.response.send_message(f"❌ Need `{role_name}` role. Use `/getinvite` then `/checkinvites`", ephemeral=True)
            return
        
        can, remaining = check_free_cooldown(guild_id, interaction.user.id)
        if not can:
            await interaction.response.send_message(f"⏳ Wait {remaining}s before using `/gen free` again.", ephemeral=True)
            return
        
        free_stock = get_server_free_stock(guild_id)
        if not free_stock:
            await interaction.response.send_message("📭 Free stock is empty.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        line = random.choice(free_stock)
        free_stock.remove(line)
        server_free_stock[guild_id] = free_stock
        save_server_stock(guild_id, send_backup=False)
        set_free_cooldown(guild_id, interaction.user.id)
        
        embed = discord.Embed(
            title="▫️ Free Account Generated",
            description=f"{interaction.user.name} generated a free account!\nCheck your DMs.",
            color=discord.Color.dark_gray()
        )
        embed.set_thumbnail(url=get_bot_avatar())
        embed.set_footer(text="made by Arxqn", icon_url=get_bot_avatar())
        await interaction.channel.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title="▫️ Free Account Details",
                description="Click the button below to copy your credentials:",
                color=discord.Color.dark_gray()
            )
            dm_embed.add_field(name="📋 Account", value=f"```{line}```", inline=False)
            dm_embed.set_footer(text="made by Arxqn")
            
            view = CopyButton(line)
            await interaction.user.send(embed=dm_embed, view=view)
            await interaction.followup.send(content="✅ Account sent to your DMs!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(content="❌ Can't DM you. Enable DMs and try again.", ephemeral=True)
            
    elif stock_type.lower() == "prem":
        prem_channels = get_server_prem_channels(guild_id)
        if interaction.channel.id not in prem_channels:
            await interaction.response.send_message("❌ Use in #prem channel.", ephemeral=True)
            return
        
        config = get_server_config(guild_id)
        role_name = config.get("prem_gen_role_name", "prem gen")
        role = discord.utils.get(interaction.user.roles, name=role_name)
        if not role and not is_admin(interaction):
            await interaction.response.send_message(f"❌ Need `{role_name}` role. Use `/redeemkey` if you have a key.", ephemeral=True)
            return
        
        can, remaining = check_prem_cooldown(guild_id, interaction.user.id)
        if not can:
            await interaction.response.send_message(f"⏳ Wait {remaining}s before using `/gen prem` again.", ephemeral=True)
            return
        
        prem_stock = get_server_prem_stock(guild_id)
        if not prem_stock:
            await interaction.response.send_message("📭 Premium stock is empty.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        line = random.choice(prem_stock)
        prem_stock.remove(line)
        server_prem_stock[guild_id] = prem_stock
        save_server_stock(guild_id, send_backup=False)
        set_prem_cooldown(guild_id, interaction.user.id)
        
        embed = discord.Embed(
            title="▪️ Premium Account Generated",
            description=f"{interaction.user.name} generated a premium account!\nCheck your DMs.",
            color=discord.Color.dark_gray()
        )
        embed.set_thumbnail(url=get_bot_avatar())
        embed.set_footer(text="made by Arxqn", icon_url=get_bot_avatar())
        await interaction.channel.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title="▪️ Premium Account Details",
                description="Click the button below to copy your credentials:",
                color=discord.Color.dark_gray()
            )
            dm_embed.add_field(name="🔐 Account", value=f"```{line}```", inline=False)
            dm_embed.set_footer(text="made by Arxqn")
            
            view = CopyButton(line)
            await interaction.user.send(embed=dm_embed, view=view)
            await interaction.followup.send(content="✅ Account sent to your DMs!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(content="❌ Can't DM you. Enable DMs and try again.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Use `free` or `prem`", ephemeral=True)

# ============================================
# REDEEMKEY COMMAND
# ============================================

@bot.tree.command(name="redeemkey", description="Redeem premium key")
async def redeemkey(interaction: discord.Interaction, key: str):
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    active_keys = get_server_active_keys(guild_id)
    
    if key not in active_keys:
        await interaction.followup.send(content="❌ Invalid key.", ephemeral=True)
        return
    data = active_keys[key]
    if data.get("used"):
        await interaction.followup.send(content="❌ Already used", ephemeral=True)
        return
    if time.time() > data["expiry"]:
        await interaction.followup.send(content="❌ Expired", ephemeral=True)
        return
    if data.get("intended_user") and data["intended_user"] != interaction.user.id:
        await interaction.followup.send(content="❌ Not your key", ephemeral=True)
        return
    data["used"] = True
    data["redeemed_by"] = interaction.user.id
    expiry = data["expiry"]
    redeemed = get_server_redeemed_users(guild_id)
    redeemed[str(interaction.user.id)] = expiry
    server_redeemed_users[guild_id] = redeemed
    save_server_keys(guild_id)
    
    config = get_server_config(guild_id)
    role_name = config.get("prem_gen_role_name", "prem gen")
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if role:
        await interaction.user.add_roles(role)
    
    hours = data.get("duration_hours", 24)
    if hours >= 24:
        days = hours // 24
        duration_display = f"{days}d" if hours % 24 == 0 else f"{days}d {hours % 24}h"
    else:
        duration_display = f"{hours}h"
    
    embed = discord.Embed(
        title="✅ Premium Activated",
        description=f"You now have prem gen role for **{duration_display}**!\nExpires: <t:{int(expiry)}:R>",
        color=discord.Color.dark_gray()
    )
    embed.set_footer(text="made by Arxqn")
    await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# CHECKPREM COMMAND
# ============================================

@bot.tree.command(name="checkprem", description="Check premium time left")
async def checkprem(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    uid = str(interaction.user.id)
    redeemed = get_server_redeemed_users(guild_id)
    
    if uid not in redeemed:
        await interaction.followup.send(content="❌ No premium time", ephemeral=True)
        return
    expiry = redeemed[uid]
    if time.time() > expiry:
        config = get_server_config(guild_id)
        role_name = config.get("prem_gen_role_name", "prem gen")
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            await interaction.user.remove_roles(role)
        await interaction.followup.send(content="❌ Premium expired", ephemeral=True)
        return
    embed = discord.Embed(title="⭐ Premium Status", description=f"Expires in {format_time_left(expiry)}\n<t:{int(expiry)}:R>", color=discord.Color.dark_gray())
    embed.set_footer(text="made by Arxqn")
    await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# CHECKINVITES COMMAND
# ============================================

@bot.tree.command(name="checkinvites", description="Check your invites")
async def checkinvites(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    uid = str(interaction.user.id)
    invite_data = get_server_invite_data(guild_id)
    count = invite_data.get(uid, 0)
    rewarded = invite_data.get(f"{uid}_rewarded", False)
    config = get_server_config(guild_id)
    
    free_role_invites = config.get("free_role_invites_required", 1)
    reward_count = config.get("invite_reward_count", 5)
    reward_hours = config.get("invite_reward_duration", "24")
    role_name = config.get("free_gen_role_name", "free gen")
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    
    embed = discord.Embed(title="📊 Your Invites", color=discord.Color.dark_gray())
    
    if count >= free_role_invites and role and role not in interaction.user.roles:
        await interaction.user.add_roles(role)
        embed.description = f"🎉 You now have the `{role.name}` role! ({count} invites)\n\n"
    else:
        embed.description = ""
    
    embed.add_field(name="People Invited", value=f"`{count}`", inline=True)
    
    if role:
        has_role = role in interaction.user.roles
        embed.add_field(name="Has free gen role", value="✅ Yes" if has_role else f"❌ No ({free_role_invites} invites needed)", inline=True)
    
    if count >= reward_count and not rewarded:
        embed.add_field(name="🎁 Reward", value=f"You've reached {reward_count} invites! A {reward_hours}-hour premium key will be sent automatically.", inline=False)
    elif count >= reward_count and rewarded:
        embed.add_field(name="🎁 Reward", value="✅ Already claimed your premium key!", inline=False)
    else:
        remaining = reward_count - count
        embed.add_field(name="🎁 Next Reward", value=f"Invite {remaining} more people to get a {reward_hours}-hour premium key!", inline=False)
    
    embed.add_field(name="📌 Note", value=f"Invited accounts must be **> {config.get('invite_age_required_days', 7)} days old** to count.\nRun `/getinvite` to get your personal invite link!", inline=False)
    embed.set_footer(text="made by Arxqn")
    await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# OTHER COMMANDS
# ============================================

class NumberModal(discord.ui.Modal, title="Enter Number"):
    def __init__(self, setting_name: str, current_value: int, guild_id: str):
        super().__init__()
        self.setting_name = setting_name
        self.guild_id = guild_id
        self.current_value = current_value
        
        self.number_input = discord.ui.TextInput(
            label=f"New value for {setting_name}",
            placeholder=f"Current: {current_value}",
            required=True,
            min_length=1,
            max_length=10
        )
        self.add_item(self.number_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.number_input.value)
            if value < 1:
                await interaction.response.send_message("❌ Value must be greater than 0.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
            return
        
        config = get_server_config(self.guild_id)
        old_value = config.get(self.setting_name)
        config[self.setting_name] = value
        server_bot_config[self.guild_id] = config
        save_server_config(self.guild_id)
        
        embed = discord.Embed(
            title="✅ Setting Updated",
            description=f"**{self.setting_name}** changed from `{old_value}` to `{value}`",
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="made by Arxqn")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        try:
            embed = create_config_embed(self.guild_id)
            view = ConfigView(self.guild_id)
            await interaction.edit_original_response(embed=embed, view=view)
        except:
            pass

class DurationModal(discord.ui.Modal, title="Enter Duration"):
    def __init__(self, setting_name: str, current_value: str, guild_id: str):
        super().__init__()
        self.setting_name = setting_name
        self.guild_id = guild_id
        self.current_value = current_value
        
        self.duration_input = discord.ui.TextInput(
            label=f"New value for {setting_name} (in hours)",
            placeholder=f"Current: {current_value} hours\nExample: 24, 48, 72, 168",
            required=True,
            min_length=1,
            max_length=10
        )
        self.add_item(self.duration_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.duration_input.value)
            if value < 1:
                await interaction.response.send_message("❌ Hours must be greater than 0.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number of hours.", ephemeral=True)
            return
        
        config = get_server_config(self.guild_id)
        old_value = config.get(self.setting_name)
        config[self.setting_name] = str(value)
        server_bot_config[self.guild_id] = config
        save_server_config(self.guild_id)
        
        embed = discord.Embed(
            title="✅ Setting Updated",
            description=f"**{self.setting_name}** changed from `{old_value}` hours to `{value}` hours",
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="made by Arxqn")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        try:
            embed = create_config_embed(self.guild_id)
            view = ConfigView(self.guild_id)
            await interaction.edit_original_response(embed=embed, view=view)
        except:
            pass

class TextModal(discord.ui.Modal, title="Enter Role Name"):
    def __init__(self, setting_name: str, current_value: str, guild_id: str):
        super().__init__()
        self.setting_name = setting_name
        self.guild_id = guild_id
        self.current_value = current_value
        
        self.text_input = discord.ui.TextInput(
            label=f"New name for {setting_name}",
            placeholder=f"Current: {current_value}",
            required=True,
            min_length=1,
            max_length=50
        )
        self.add_item(self.text_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        value = self.text_input.value.strip()
        
        config = get_server_config(self.guild_id)
        old_value = config.get(self.setting_name)
        config[self.setting_name] = value
        server_bot_config[self.guild_id] = config
        save_server_config(self.guild_id)
        
        embed = discord.Embed(
            title="✅ Setting Updated",
            description=f"**{self.setting_name}** changed from `{old_value}` to `{value}`",
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="made by Arxqn")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        try:
            embed = create_config_embed(self.guild_id)
            view = ConfigView(self.guild_id)
            await interaction.edit_original_response(embed=embed, view=view)
        except:
            pass

class ConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=120)
        self.guild_id = str(guild_id)
    
    @discord.ui.button(label="📝 Free Gen Role Name", style=discord.ButtonStyle.secondary, row=0)
    async def free_role_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("free_gen_role_name", "free gen")
        modal = TextModal("free_gen_role_name", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⭐ Prem Gen Role Name", style=discord.ButtonStyle.secondary, row=0)
    async def prem_role_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("prem_gen_role_name", "prem gen")
        modal = TextModal("prem_gen_role_name", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🎁 Free Role Invites Required", style=discord.ButtonStyle.primary, row=1)
    async def free_role_invites(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("free_role_invites_required", 1)
        modal = NumberModal("free_role_invites_required", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🎁 Premium Reward Invites", style=discord.ButtonStyle.primary, row=1)
    async def reward_count(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("invite_reward_count", 5)
        modal = NumberModal("invite_reward_count", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📅 Invite Age Required", style=discord.ButtonStyle.primary, row=1)
    async def age_required(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("invite_age_required_days", 7)
        modal = NumberModal("invite_age_required_days", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⏱️ Reward Duration (Hours)", style=discord.ButtonStyle.primary, row=2)
    async def reward_duration(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("invite_reward_duration", "24")
        modal = DurationModal("invite_reward_duration", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⏱️ Free Cooldown", style=discord.ButtonStyle.primary, row=2)
    async def free_cooldown(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("default_free_cooldown", 30)
        modal = NumberModal("default_free_cooldown", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⏱️ Prem Cooldown", style=discord.ButtonStyle.primary, row=2)
    async def prem_cooldown(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_server_config(self.guild_id)
        current = config.get("default_prem_cooldown", 30)
        modal = NumberModal("default_prem_cooldown", current, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔁 Reset to Defaults", style=discord.ButtonStyle.danger, row=3)
    async def reset_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        server_bot_config[self.guild_id] = DEFAULT_CONFIG.copy()
        save_server_config(self.guild_id)
        embed = discord.Embed(title="✅ Settings Reset", description="All settings have been reset to default values.", color=discord.Color.dark_gray())
        embed.set_footer(text="made by Arxqn")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        embed = create_config_embed(self.guild_id)
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.gray, row=3)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Config menu closed.", ephemeral=True)
        self.stop()

def create_config_embed(guild_id):
    config = get_server_config(guild_id)
    embed = discord.Embed(
        title="⚙️ Bot Configuration",
        description="Click the buttons below to change settings.\n\n**Current Settings:**",
        color=discord.Color.dark_gray()
    )
    
    embed.add_field(name="📝 Free Gen Role", value=f"`{config.get('free_gen_role_name', 'free gen')}`", inline=True)
    embed.add_field(name="⭐ Prem Gen Role", value=f"`{config.get('prem_gen_role_name', 'prem gen')}`", inline=True)
    embed.add_field(name="🎁 Free Role Invites", value=f"`{config.get('free_role_invites_required', 1)}` invites", inline=True)
    embed.add_field(name="🎁 Premium Reward Invites", value=f"`{config.get('invite_reward_count', 5)}` invites", inline=True)
    embed.add_field(name="📅 Invite Age Required", value=f"`{config.get('invite_age_required_days', 7)}` days", inline=True)
    embed.add_field(name="⏱️ Reward Duration", value=f"`{config.get('invite_reward_duration', '24')}` hours", inline=True)
    embed.add_field(name="⏱️ Free Cooldown", value=f"`{config.get('default_free_cooldown', 30)}` sec", inline=True)
    embed.add_field(name="⏱️ Prem Cooldown", value=f"`{config.get('default_prem_cooldown', 30)}` sec", inline=True)
    
    embed.set_footer(text="made by Arxqn")
    return embed

@bot.tree.command(name="config", description="[ADMIN] Open interactive config menu")
async def config_cmd(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    embed = create_config_embed(guild_id)
    view = ConfigView(guild_id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="setcooldown", description="[ADMIN] Set cooldown for /gen (free or prem)")
@app_commands.describe(stock_type="free or prem", seconds="Cooldown in seconds")
async def setcooldown(interaction: discord.Interaction, stock_type: str, seconds: int):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    config = get_server_config(guild_id)
    
    if stock_type.lower() == "free":
        config["default_free_cooldown"] = seconds
        server_bot_config[guild_id] = config
        save_server_config(guild_id)
        await interaction.followup.send(f"✅ Free gen cooldown set to {seconds}s", ephemeral=True)
    elif stock_type.lower() == "prem":
        config["default_prem_cooldown"] = seconds
        server_bot_config[guild_id] = config
        save_server_config(guild_id)
        await interaction.followup.send(f"✅ Premium gen cooldown set to {seconds}s", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `free` or `prem`", ephemeral=True)

@bot.tree.command(name="getinvite", description="Get personal invite link")
async def getinvite(interaction: discord.Interaction):
    try:
        invite = await interaction.channel.create_invite(max_uses=1, max_age=86400, unique=True)
        config = get_server_config(str(interaction.guild.id))
        free_role_invites = config.get("free_role_invites_required", 1)
        reward_count = config.get("invite_reward_count", 5)
        reward_hours = config.get("invite_reward_duration", "24")
        age_days = config.get("invite_age_required_days", 7)
        embed = discord.Embed(
            title="🔗 Your Invite Link",
            description=f"**{invite.url}**\n\n"
                        f"**Rewards:**\n"
                        f"• {free_role_invites} invite → free gen role\n"
                        f"• {reward_count} invites → {reward_hours}-hour premium key\n"
                        f"Accounts must be >{age_days} days old\n\n"
                        f"**After inviting someone, run `/checkinvites` to get your role!**",
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="made by Arxqn")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except:
        await interaction.response.send_message("❌ Bot needs Create Invite permission", ephemeral=True)

@bot.tree.command(name="setfreechannel", description="[ADMIN] Set free gen channel")
async def setfreechannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    free_channels = get_server_free_channels(guild_id)
    
    if channel.id not in free_channels:
        free_channels.append(channel.id)
        server_free_channels[guild_id] = free_channels
        save_server_channels(guild_id)
    await interaction.followup.send(f"✅ Free gen works in {channel.mention}", ephemeral=True)

@bot.tree.command(name="setpremchannel", description="[ADMIN] Set premium gen channel")
async def setpremchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    guild_id = str(interaction.guild.id)
    prem_channels = get_server_prem_channels(guild_id)
    
    if channel.id not in prem_channels:
        prem_channels.append(channel.id)
        server_prem_channels[guild_id] = prem_channels
        save_server_channels(guild_id)
    await interaction.followup.send(f"✅ Premium gen works in {channel.mention}", ephemeral=True)

@bot.tree.command(name="addfreerole", description="[ADMIN] Manually give free gen role")
async def addfreerole(interaction: discord.Interaction, member: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    config = get_server_config(str(interaction.guild.id))
    role_name = config.get("free_gen_role_name", "free gen")
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if not role:
        await interaction.followup.send(f"❌ Role '{role_name}' not found", ephemeral=True)
        return
    await member.add_roles(role)
    await interaction.followup.send(f"✅ Gave free gen role to {member.mention}", ephemeral=True)

# ============================================
# ON MESSAGE (No ping handling)
# ============================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

# ============================================
# RUN BOT
# ============================================

# NEVER HARDCODE YOUR TOKEN - use environment variables
token = os.environ.get("DISCORD_BOT_TOKEN")
if not token:
    raise RuntimeError("DISCORD_BOT_TOKEN environment variable not set")

bot.run(token)
