import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

print("🚀 SCRIPT STARTET", flush=True)

# 🔐 ENV
TOKEN = os.getenv("TOKEN")

channel_id_env = os.getenv("CHANNEL_ID")

if channel_id_env is None:
    print("❌ CHANNEL_ID fehlt!", flush=True)
    CHANNEL_ID = None
else:
    CHANNEL_ID = int(channel_id_env)
    print(f"✅ CHANNEL_ID geladen: {CHANNEL_ID}", flush=True)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


# 🔧 NUR HIER WURDE ETWAS GEÄNDERT (XML FIX)
def get_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print("❌ Fehler beim Laden der Daten", flush=True)
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"❌ XML kaputt → retry später: {e}", flush=True)
            return None  # ← WICHTIG

        events = []

        for event in root.findall("event"):
            title = event.findtext("title")
            impact = event.findtext("impact")
            date = event.findtext("date")
            time_ = event.findtext("time")

            if impact not in ["High", "Medium"]:
                continue

            events.append({
                "title": title,
                "impact": impact,
                "date": date,
                "time": time_
            })

        print(f"✅ {len(events)} Events geladen", flush=True)
        return events

    except Exception as e:
        print(f"❌ Fehler: {e}", flush=True)
        return []


@client.event
async def on_ready():
    print(f"🤖 Eingeloggt als {client.user}", flush=True)
    print("🟢 Bot ist ready → starte Loop", flush=True)
    client.loop.create_task(news_loop())


async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    while not client.is_closed():
        now = datetime.utcnow() + timedelta(hours=2)
        print(f"⏰ Check um {now}", flush=True)

        events = get_events()

        # 🔧 NUR DAS HIER IST NEU
        if events is None:
            print("⏳ XML war kaputt → neuer Versuch in 30 Sekunden", flush=True)
            await asyncio.sleep(30)
            continue

        print(f"📊 {len(events)} Events geladen", flush=True)

        for event in events:
            print(f"📊 EVENT: {event['title']} |", flush=True)

        await asyncio.sleep(60)


client.run(TOKEN)
