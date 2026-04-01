import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import os
import sys

# 🔥 sofortige Logs
sys.stdout.reconfigure(line_buffering=True)

print("🚀 SCRIPT STARTET", flush=True)

# 🔐 ENV
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# Discord Setup
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# 🔁 Speicher
sent_events = set()
pre_alerts_1h = set()
pre_alerts_30m = set()
last_events = []
loop_started = False

# 🔥 EVENTS LADEN
def get_events():
    global last_events

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        if not response.content or b"<" not in response.content:
            print("❌ Kein gültiges XML → nutze Cache", flush=True)
            return last_events

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"❌ XML kaputt → nutze Cache: {e}", flush=True)
            return last_events

        events = []

        for event in root.findall("event"):
            title = event.findtext("title", default="N/A")
            country = event.findtext("country", default="N/A")
            date = event.findtext("date", default="")
            time_ = event.findtext("time", default="")

            impact = event.findtext("impact", default="low").lower()
            if impact not in ["high", "3", "medium"]:
                continue

            events.append({
                "title": title,
                "country": country,
                "date": date,
                "time": time_,
                "impact": impact
            })

        print(f"✅ {len(events)} Events geladen", flush=True)

        last_events = events
        return events

    except Exception as e:
        print(f"❌ Fehler beim Laden → nutze Cache: {e}", flush=True)
        return last_events

# 🔁 LOOP
async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    print("🟢 Bot ist ready → starte Loop", flush=True)

    while not client.is_closed():
        try:
            now = datetime.now(timezone.utc) + timedelta(hours=2)
            print(f"⏰ Check um {now}", flush=True)

            events = get_events()

            # 🧪 TEST EVENT (2 Minuten in Zukunft)
            test_time = now + timedelta(minutes=2)
            events.append({
                "title": "TEST NEWS",
                "country": "USD",
                "date": test_time.strftime("%Y-%m-%d"),
                "time": test_time.strftime("%H:%M"),
                "impact": "high"
            })

            for event in events:
                title = event["title"]
                country = event["country"]
                date = event["date"]
                time_ = event["time"]

                if time_ == "All Day" or time_ == "":
                    continue

                try:
                    event_time = datetime.strptime(
                        f"{date} {time_}", "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=timezone.utc)
                except:
                    continue

                key = f"{title}_{date}_{time_}"
                diff = (event_time - now).total_seconds()

                # 🔔 1h vorher
                if 0 < diff <= 3900:
                    if key not in pre_alerts_1h:
                        msg = f"🔔 **In 1 Stunde:** {country} - {title} ({time_})"
                        await channel.send(msg)
                        print(f"🔔 1h Alert: {title}", flush=True)
                        pre_alerts_1h.add(key)

                # ⏳ 30min vorher
                if 0 < diff <= 2100:
                    if key not in pre_alerts_30m:
                        msg = f"⏳ **In 30 Minuten:** {country} - {title} ({time_})"
                        await channel.send(msg)
                        print(f"⏳ 30m Alert: {title}", flush=True)
                        pre_alerts_30m.add(key)

                # 📤 beim Event
                if 0 < diff <= 300:
                    if key not in sent_events:
                        msg = f"📊 **JETZT:** {country} - {title} ({time_})"
                        await channel.send(msg)
                        print(f"📤 Event gesendet: {title}", flush=True)
                        sent_events.add(key)

        except Exception as e:
            print(f"❌ Loop Fehler: {e}", flush=True)

        await asyncio.sleep(60)

# 🤖 TEST
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if "test" in message.content.lower():
        await message.channel.send("🤖 Bot läuft!")
        print("💬 Test Antwort gesendet", flush=True)

# 🚀 START
@client.event
async def on_ready():
    global loop_started

    print(f"🤖 Eingeloggt als {client.user}", flush=True)

    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True

client.run(TOKEN)
