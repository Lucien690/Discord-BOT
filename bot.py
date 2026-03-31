import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

print("🚀 SCRIPT STARTET")

# 🔐 ENV
TOKEN = os.getenv("TOKEN")

channel_id_env = os.getenv("CHANNEL_ID")

if channel_id_env is None:
    print("❌ CHANNEL_ID fehlt!")
    CHANNEL_ID = None
else:
    CHANNEL_ID = int(channel_id_env)
    print(f"✅ CHANNEL_ID geladen: {CHANNEL_ID}")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

posted_events = set()

# Safe XML
def safe_find(event, tag):
    found = event.find(tag)
    return found.text.strip() if found is not None and found.text else ""

# Events holen
def get_events():
    print("🔄 Lade Events...")

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print("❌ API Fehler")
            return []

        try:
            root = ET.fromstring(response.content)
        except Exception as e:
            print(f"❌ XML ERROR: {e}")
            return []

    except Exception as e:
        print(f"❌ REQUEST ERROR: {e}")
        return []

    events_list = []

    for event in root.findall("event"):
        impact = safe_find(event, "impact")

        if impact not in ["Medium", "High"]:
            continue

        title = safe_find(event, "title")
        currency = safe_find(event, "currency")
        actual = safe_find(event, "actual")
        forecast = safe_find(event, "forecast")

        events_list.append({
            "title": title,
            "currency": currency,
            "actual": actual,
            "forecast": forecast
        })

    print(f"✅ {len(events_list)} Events gefunden")

    return events_list

# LOOP
async def news_loop():
    print("🟡 news_loop gestartet (warte auf ready)")

    await client.wait_until_ready()

    print("🟢 Bot ist ready → starte Loop")

    if CHANNEL_ID is None:
        print("❌ Kein Channel → STOP")
        return

    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("❌ Channel nicht gefunden!")
        return

    print("🚀 NEWS LOOP STARTED")

    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=2)
            print(f"⏰ Check um {now}")

            events = get_events()

            for event in events:
                print(f"📊 EVENT: {event['title']} | {event['actual']}")

                if event["actual"] and event["title"] not in posted_events:

                    direction = "Neutral"

                    try:
                        actual_val = float(event["actual"].replace("%", "").replace(",", "."))
                        forecast_val = float(event["forecast"].replace("%", "").replace(",", "."))

                        if actual_val > forecast_val:
                            direction = "Bullish 📈"
                        elif actual_val < forecast_val:
                            direction = "Bearish 📉"
                    except:
                        pass

                    message = (
                        f"🚨 **{event['currency']} News**\n"
                        f"📊 {event['title']}\n\n"
                        f"Actual: {event['actual']}\n"
                        f"Forecast: {event['forecast']}\n\n"
                        f"➡️ Impact: {direction}"
                    )

                    print(f"📤 Sende Nachricht: {event['title']}")

                    await channel.send(message)

                    posted_events.add(event["title"])

        except Exception as e:
            print(f"❌ LOOP ERROR: {e}")

        await asyncio.sleep(60)

# READY EVENT
@client.event
async def on_ready():
    print("🔥 ON_READY WURDE AUSGEFÜHRT")
    print(f"👤 Eingeloggt als {client.user}")
    print(f"🔎 CHANNEL_ID: {CHANNEL_ID}")

    client.loop.create_task(news_loop())

# TEST
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        print("💬 Bot wurde erwähnt")
        await message.channel.send("Bot funktioniert ✅")

# START
client.run(TOKEN)
