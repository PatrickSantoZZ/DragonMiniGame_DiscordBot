from dotenv import dotenv_values
import os, json, asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import random

# db
from database import init_db, get_user, update_last_daily, update_last_worked, update_balance, update_last_flip, get_top_users, add_to_inventory, get_inventory_item, remove_from_inventory, get_inventory

config = dotenv_values(".env")
TOKEN = config["DISCORD_TOKEN"]
env_channels = config.get("ALLOWED_CHANNELS", "")
WORK_COOLDOWN_HOURS = int(config.get("WORK_COOLDOWN_HOURS", 3))
DAILY_COOLDOWN_HOURS = int(config.get("DAILY_COOLDOWN_HOURS", 24))
FLIP_COOLDOWN_HOURS = int(config.get("FLIP_COOLDOWN_HOURS", 1))
allowed_channels = {}
active_towers = {} # tower minigame
ENTRY_FEE = 1000 # entry fee for the token minigame

for pair in env_channels.split(","):
    if ":" in pair:
        guild_id, channel_id = pair.split(":")
        allowed_channels[int(guild_id)] = int(channel_id)
        print(f"guild_id: {guild_id}, channel_id: {channel_id} added to allowed_channels")

client = commands.Bot(command_prefix="?c", intents=discord.Intents.all())
tree = client.tree
# -----------------------------------
# Events
# -----------------------------------
@client.event
async def on_ready():
    await client.change_presence(
        status=discord.Status.dnd,
        activity=discord.Activity(type=discord.ActivityType.competing, name="Buddelt nach Winkler Token")
    )
    print(f'{client.user} is connected to the following guilds:')

    for guild in client.guilds:
        # chunking to be more efficient tbh
        await guild.chunk()

        for member in guild.members:
            if not member.bot:
                await asyncio.to_thread(get_user, member.id)

        print(f' - {guild.name} (id: {guild.id})')

    command_sync = await tree.sync()
    print(f"Registered users and synced {len(command_sync)} commands for {len(client.guilds)} servers")

# add new user to DB on member join event :salute:
@client.event
async def on_member_join(member):
    if not member.bot:
        await asyncio.to_thread(get_user, member.id)

# -----------------------------------
# Functions
# -----------------------------------
# make sure the user is only using the slash commands in a server not in the bot's DMs and its only in a specific channel(server based)
def allowed_channel_only():
    def predicate(interaction: discord.Interaction):
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id
        #print(f"guild_id: {guild_id}, channel_id: {channel_id}")
        if guild_id is None:
            raise app_commands.CheckFailure("Dieser Command kann nur in Servern verwendet werden.")
        allowed_channel = allowed_channels.get(guild_id)
        #print(f"allowed_channel: {allowed_channel}")
        if allowed_channel != channel_id:
            raise app_commands.CheckFailure("Dieser Command darf nur im erlaubten Channel benutzt werden.")
        return True
    return app_commands.check(predicate)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            f"❌ {error.args[0]}", ephemeral=True
        )
# give higher cash multiplier for people that boost the server to reward them a bit for helping us out :3
async def get_multiplier(interaction: discord.Interaction) -> int:
    member = interaction.guild.get_member(interaction.user.id)
    print(f"member: {member}")
    if member and member.premium_since:
        return 2  # Booster multiplier
    return 1  # Normal users

# helper function to convert numbers to emotes (lootbox opening command)
number_emotes = {
    "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
    "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣"
}
def number_to_emote(number: int) -> str:
    return ''.join(number_emotes.get(d, d) for d in str(number))

# helper function for the tower minigame
def _generate_tiles():
    correct_tile = random.randint(1, 3)
    return [i == correct_tile for i in range(1, 4)]
# -----------------------------------
# Slash Commands
# -----------------------------------
# work / buddeln command start
@allowed_channel_only()
@tree.command(name="buddeln", description="Verdiene Winkler Token")
async def buddeln(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    user_id = interaction.user.id
    multiplier = await get_multiplier(interaction)

    user_data = get_user(user_id)
    print(f"user_data: {user_data} multiplier for this user is {multiplier}")
    now = datetime.now(ZoneInfo("Europe/Berlin"))

    if user_data and user_data.get("last_worked"):
        last_worked_str = user_data["last_worked"]
        last_worked = datetime.fromisoformat(last_worked_str)
        cooldown_end = last_worked + timedelta(hours=WORK_COOLDOWN_HOURS)

        if now < cooldown_end:
            print(f"cooldown active for user {user_id}")
            remaining = cooldown_end - now
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return await interaction.followup.send(f"Du kannst noch {hours} Stunden und {minutes} Minuten warten bevor du wieder buddeln kannst!.", ephemeral=True)
    
    
    # no cooldown?
    update_last_worked(user_id, now.isoformat())
    #print(f"updated last_worked for user {user_id}")
    reward = random.randint(450, 550) * multiplier # random reward between x and y Winkler Token * multiplier (normal user x1, booster x2)
    update_balance(user_id, reward)
    # tell the user how much he earned :3
    await interaction.followup.send(f"Du hast gebuddelt und **{reward}** Winkler Token💶 erhalten!", ephemeral=True)

# daily / reward command start
@allowed_channel_only()
@tree.command(name="daily", description="Erhalte dein tägliches Geschenk")
async def daily(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    user_id = interaction.user.id
    multiplier = await get_multiplier(interaction)

    user_data = get_user(user_id)
    print(f"user_data: {user_data} multiplier for this user is {multiplier}")

    now = datetime.now(ZoneInfo("Europe/Berlin"))

    if user_data and user_data.get("last_daily"):
        print(f"checking daily cooldown for user {user_id}")
        last_daily_str = user_data["last_daily"]
        if last_daily_str:
            last_daily = datetime.fromisoformat(last_daily_str)
            cooldown_end = last_daily + timedelta(hours=DAILY_COOLDOWN_HOURS)

            if now < cooldown_end:
                remaining = cooldown_end - now
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                return await interaction.followup.send(
                    f"Du kannst dein tägliches Geschenk erst in {hours} Stunden und {minutes} Minuten wieder abholen.", ephemeral=True
                )

    # no cooldown => reward the user
    update_last_daily(user_id, now.isoformat())
    reward = random.randint(1000, 1500) * multiplier
    update_balance(user_id, reward) # give daily reward 1000-1500 Winkler Token
    add_to_inventory(user_id, "Lootbox", 1)

    await interaction.followup.send(
        f"🎁 Du hast dein tägliches Geschenk erhalten und bekommst **{reward}** Winkler Token und eine Lootbox!", ephemeral=True
    )
 
# get user balance
@allowed_channel_only()
@tree.command(name="balance", description="Zeigt das Token-Guthaben eines Nutzers")
@app_commands.describe(user="Der Nutzer, dessen Guthaben du sehen möchtest")
async def balance(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    user_data = get_user(target_user.id)

    if user_data is None:
        await interaction.response.send_message("⚠️ Profil nicht gefunden.", ephemeral=True)
        return

    balance = user_data["balance"]
    if target_user.id == interaction.user.id:
        msg = f"💰 Du hast aktuell **{balance}** Winkler Token."
    else:
        msg = f"💰 {target_user.display_name} hat aktuell **{balance}** Winkler Token."
    await interaction.response.send_message(msg, ephemeral=True)

# flip a coin command
@allowed_channel_only()
@tree.command(name="flip", description="Wette auf Kopf oder Zahl und gewinne Winkler Token!")
@app_commands.describe(choice="Kopf oder Zahl", amount="Wie viele Token willst du setzen?")
async def flip(interaction: discord.Interaction, choice: str, amount: int):
    await interaction.response.defer(thinking=True,ephemeral=True) 
    #print(f"step 1 choice: {choice}, amount: {amount}")
    choice = choice.lower()
    if choice not in ["kopf", "zahl"]:
        #print(f"step 1 fail: choice: {choice}, amount: {amount}")
        return await interaction.followup.send("❌ Bitte wähle `Kopf` oder `Zahl`.", ephemeral=True)

    user_id = interaction.user.id
    user_data = get_user(user_id)
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    #print(f"step 2 : user_data: {user_data}")

    # Cooldown check
    if user_data and user_data.get("last_flip"):
        try:
            last_flip = datetime.fromisoformat(user_data["last_flip"])
            #print(f" step 3 last_flip: {last_flip}")
            cooldown_end = last_flip + timedelta(hours=1)
            if now < cooldown_end:
                #print(f"step 4 now: {now}, cooldown_end: {cooldown_end}")
                remaining = cooldown_end - now
                minutes = remaining.seconds // 60
                return await interaction.followup.send(
                    f"⏳ Du musst noch **{minutes} Minuten** warten, bevor du wieder flippen kannst.", ephemeral=True
                )
        except Exception as e:
            print(f"Error parsing last_flip: {e}")  # just in case

    #print(f"step 5 user_data: {user_data}")
    # Balance check
    balance = user_data["balance"]
    if amount <= 0:
        return await interaction.followup.send("❌ Der Einsatz muss größer als 0 sein.", ephemeral=True)
    if balance < amount:
        return await interaction.followup.send("❌ Du hast nicht genug Winkler Token.", ephemeral=True)

    # Game logic
    result = random.choice(["kopf", "zahl"])
    win = (choice == result)

    #print(f"step 6 result: {result}, win: {win}")
    update_last_flip(user_id, now.isoformat())


    if win:
        update_balance(user_id, amount)  # Add the bet amount (double payout)
        result_msg = f"🎉 Es war **{result.capitalize()}**! Du hast **{amount}** Winkler Token gewonnen!"
    else:
        update_balance(user_id, -amount)  # Subtract the bet amount
        result_msg = f"😢 Es war **{result.capitalize()}**. Du hast **{amount}** Winkler Token verloren."

    #print(f"step 7 result_msg: {result_msg}")
    await interaction.followup.send(result_msg, ephemeral=True)

@allowed_channel_only()
@tree.command(name="leaderboard", description="Zeigt die Top 10 mit dem meisten Winkler Token")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    top_users = get_top_users(limit=10)
    embed = discord.Embed(
        title="🏆 Top 10 Benutzer – Meiste Winkler Token",
        description=f"Stand: {datetime.now(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y um %H:%M Uhr')}",
        color=discord.Color.dark_gold()
    )

    medals = ["🥇", "🥈", "🥉"]

    leaderboard_text = ""
    for rank, user in enumerate(top_users, start=1):
        member = interaction.guild.get_member(user["user_id"])
        name = member.display_name if member else f"Unbekannt ({user['user_id']})"
        medal = medals[rank - 1] if rank <= 3 else f"#{rank}"
        leaderboard_text += f"**{medal} {name}**\nToken: `{user['balance']}`\n\n"

    embed.description = leaderboard_text

    await interaction.followup.send(embed=embed)

@allowed_channel_only()
@tree.command(name="inventory", description="Zeigt dein Inventar")
async def inventory(interaction: discord.Interaction):
    user_id = interaction.user.id
    items = get_inventory(user_id)

    if not items:
        await interaction.response.send_message("🎒 Dein Inventar ist leer!", ephemeral=True)
        return

    embed = discord.Embed(title="🎒 Dein Inventar", color=discord.Color.blurple())
    for name, quantity in items:
        emoji = {
            "Lootbox": "🎁",
            "XP-Boost": "🧪",
            "Premium-Ticket": "💎"
        }.get(name, "📦")

        embed.add_field(name=f"{emoji} {name}", value=f"× {quantity}", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# lootbox opening
@allowed_channel_only()
@tree.command(name="lootbox", description="Öffnet eine oder mehrere Lootboxen.")
@app_commands.describe(amount="Wie viele Lootboxen möchtest du öffnen?")
async def lootbox(interaction: discord.Interaction, amount: int = 1):
    await interaction.response.defer(thinking=True, ephemeral=True)
    user_id = interaction.user.id

    # Check inventory
    lootbox_count = get_inventory_item(user_id, "Lootbox")
    if lootbox_count is None or lootbox_count < amount:
        return await interaction.followup.send(
            f"❌ Du besitzt nicht genug 🎁 **Lootboxen**! (Besitzt: {lootbox_count})", ephemeral=True)

    # Consume lootboxes
    remove_from_inventory(user_id, "Lootbox", amount)

    golden_boxes = 0
    total_tokens = 0
    results = []

    msg = await interaction.followup.send(f"🎁 Öffne {amount}x Lootbox...", wait=True)

    for i in range(amount):
        roll = random.randint(1, 100)

        # Fake animation
        fake = number_to_emote(random.randint(1000, 2800))
        await asyncio.sleep(0.6)
        await msg.edit(content=f"🔄 {fake} ({i+1}/{amount})")

        await asyncio.sleep(0.3)

        if roll == 1:
            golden_boxes += 1
            results.append("✨ Goldene Lootbox")
        elif roll <= 21:
            amt = random.randint(2000, 2800)
            total_tokens += amt
            results.append(f"💸 {amt} Tokens")
        else:
            amt = random.randint(500, 1500)
            total_tokens += amt
            results.append(f"💰 {amt} Tokens")

    # Apply rewards
    if golden_boxes > 0:
        add_to_inventory(user_id, "Goldene Lootbox", golden_boxes)
    if total_tokens > 0:
        update_balance(user_id, total_tokens)

    # Build final message
    summary = (
        f"🎁 **{amount}x Lootbox geöffnet!**\n\n"
        f"{f'✨ {golden_boxes}x Goldene Lootbox\n' if golden_boxes else ''}"
        f"💰 Insgesamt **{total_tokens}** Winkler Token\n"
    )

    await msg.edit(content=summary)


# buy lootbox
@allowed_channel_only()
@tree.command(name="buylootbox", description="Kaufe eine oder mehrere Lootboxen für je 1500 Winkler Token.")
@app_commands.describe(amount="Wie viele Lootboxen möchtest du kaufen?")
async def buylootbox(interaction: discord.Interaction, amount: int = 1):
    await interaction.response.defer(ephemeral=True)

    user_id = interaction.user.id
    user_data = get_user(user_id)

    if not user_data:
        return await interaction.followup.send("❌ Benutzer nicht gefunden.", ephemeral=True)

    if amount <= 0:
        return await interaction.followup.send("❌ Ungültige Menge.", ephemeral=True)

    cost = 1500 * amount
    balance = user_data["balance"]

    if balance < cost:
        return await interaction.followup.send(
            f"❌ Du hast nicht genug Winkler Token! (Benötigt: {cost}, Dein Kontostand: {balance})", ephemeral=True)

    update_balance(user_id, -cost)
    add_to_inventory(user_id, "Lootbox", amount)

    await interaction.followup.send(
        f"🎁 Du hast erfolgreich **{amount}x Lootbox**{'en' if amount != 1 else ''} für **{cost}** Winkler Token gekauft!",
        ephemeral=True)

# tower minigame main command
@allowed_channel_only()
@tree.command(name="tower", description="Beginne das Tower Minigame!")
async def tower(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    if user_id in active_towers:
        return await interaction.followup.send("❗ Du spielst bereits ein Tower-Spiel. Nutze `/climb <1-3>` oder `/cashout`!", ephemeral=True)

    user_data = get_user(user_id)
    if not user_data or user_data["balance"] < ENTRY_FEE:
        return await interaction.followup.send(
            f"🚫 Du brauchst mindestens {ENTRY_FEE} Winkler Token, um das Spiel zu starten.",
            ephemeral=True
        )

    update_balance(user_id, -ENTRY_FEE)

    game_data = {
        "level": 0,
        "reward": 0,
        "tiles": _generate_tiles(),
        "lost": False
    }
    active_towers[user_id] = game_data

    await interaction.followup.send(
        f"🗼 Tower Spiel gestartet für {ENTRY_FEE} Winkler Token!\nLevel 0 – Wähle eine von 3 Kacheln mit `/climb <1-3>`.",
        ephemeral=True
    )

# tower minigame climb
@allowed_channel_only()
@tree.command(name="climb", description="Klettere eine weitere Stufe im Tower Spiel.")
@app_commands.describe(tile="Welche Kachel? 1, 2 oder 3")
async def climb(interaction: discord.Interaction, tile: int):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    if user_id not in active_towers:
        return await interaction.followup.send("⚠️ Du hast kein laufendes Tower-Spiel.", ephemeral=True)

    game = active_towers[user_id]
    if game["lost"]:
        return await interaction.followup.send("☠️ Du hast bereits verloren. Starte ein neues Spiel mit `/tower`.", ephemeral=True)

    if tile < 1 or tile > 3:
        return await interaction.followup.send("❌ Ungültige Kachel. Wähle zwischen 1 und 3.", ephemeral=True)

    if not game["tiles"][tile - 1]:
        game["lost"] = True
        active_towers.pop(user_id, None)
        return await interaction.followup.send("💥 Falsche Wahl! Du bist abgestürzt und verlierst alles!", ephemeral=True)

    game["level"] += 1
    reward = int(ENTRY_FEE * (1.5 ** game["level"]))  # exponential-ish reward
    game["reward"] = reward
    game["tiles"] = _generate_tiles()

    await interaction.followup.send(
        f"✅ Richtig! Du bist jetzt auf Level {game['level']}.\nAktueller Gewinn: **{reward}** Winkler Token.\nWeiter mit `/climb <1-3>` oder stoppe mit `/cashout`.",
        ephemeral=True
    )

# tower minigame cashout
@allowed_channel_only()
@tree.command(name="cashout", description="Beende das Tower Spiel und nimm deinen Gewinn mit.")
async def cashout(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    if user_id not in active_towers:
        return await interaction.followup.send("❗ Du hast kein aktives Tower-Spiel.", ephemeral=True)

    game = active_towers.pop(user_id)
    if game["lost"]:
        return await interaction.followup.send("☠️ Du hast bereits verloren.", ephemeral=True)

    reward = game["reward"]
    update_balance(user_id, reward)

    await interaction.followup.send(
        f"💸 Du hast erfolgreich ausgezahlt und erhältst **{reward}** Winkler Token!\n🏁 Spiel beendet.",
        ephemeral=True
    )












if __name__ == "__main__":
    init_db()
    client.run(TOKEN)