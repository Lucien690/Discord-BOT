import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

# 🔐 ENV VARS
TOKEN = os.getenv("TOKEN")

channel_id_env = os.getenv("CHANNEL_ID")
if channel_id_env is None:
    print("❌ CHANNEL_ID fehlt!")
    CHANNEL_ID = None
else:
    CHANNEL_ID = int(channel_id_env)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

posted_events = set()

# Sicheres XML Lesen
def safe_find(event, tag):
    found = event.find(tag)
    return found.text.strip() if found is not None and found.text else ""

# Events holen (mit Fehler-Schutz)
def get_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print("❌ API nicht erreichbar")
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

    return events_list

# MAIN LOOP
async def news_loop():
    await client.wait_until_ready()

    if CHANNEL_ID is None:
        print("❌ Kein Channel gesetzt → Bot stoppt")
        return

    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("❌ Channel nicht gefunden!")
        return

    print("🚀 NEWS LOOP STARTED")

    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=2)

            events = get_events()

            for event in events:
                print(f"📊 EVENT: {event['title']} | ACTUAL: {event['actual']}")

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

                    print(f"📤 SENDING: {event['title']}")

                    await channel.send(message)

                    posted_events.add(event["title"])

        except Exception as e:
            print(f"❌ LOOP ERROR: {e}")

        await asyncio.sleep(60)

# BOT START
@client.event
async def on_ready():
    print(f"✅ FOREX BOT ONLINE als {client.user}")
    print(f"🔎 CHANNEL_ID: {CHANNEL_ID}")

    client.loop.create_task(news_loop())

# TEST MIT @BOT
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        await message.channel.send("Bot funktioniert ✅")

client.run(TOKEN)
