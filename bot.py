import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import sys

# 🔥 Logs sofort anzeigen
sys.stdout.reconfigure(line_buffering=True)

print("🚀 SCRIPT STARTET", flush=True)

# 🔐 ENV
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# 📊 Sets
posted_events = set()
pre_alerted_events = set()

# 🤖 Discord Setup
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# 🔥 FIXED XML FUNCTION
def get_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        # 🔥 XML robuster machen
        content = response.content.decode("utf-8", errors="ignore")

        # Problematische Zeichen fixen
        content = content.replace("&", "&amp;")

        root = ET.fromstring(content)

    except Exception as e:
        print(f"❌ XML Fehler (skip): {e}", flush=True)
        return []

    events = []

    for event in root.findall("event"):
        try:
            title = event.find("title")
            time = event.find("time")
            actual = event.find("actual")

            title = title.text if title is not None else None
            time = time.text if time is not None else None
            actual = actual.text if actual is not None else None

            events.append({
                "title": title,
                "time": time,
                "actual": actual
            })

        except Exception as e:
            print(f"❌ Event Fehler: {e}", flush=True)
            continue

    print(f"✅ {len(events)} Events geladen", flush=True)
    return events


async def news_loop():
    await client.wait_until_ready()
    print("🟢 Bot ist ready → starte Loop", flush=True)

    while not client.is_closed():
        try:
            now = datetime.utcnow() + timedelta(hours=2)
            print(f"⏰ Check um {now}", flush=True)

            events = get_events()

            for event in events:
                try:
                    title = event.get("title")
                    time_str = event.get("time")
                    actual = event.get("actual")

                    if not title or not time_str:
                        continue

                    # 🕒 Zeit parsen
                    try:
                        event_time = datetime.strptime(time_str, "%H:%M")
                        event_time = event_time.replace(
                            year=now.year,
                            month=now.month,
                            day=now.day
                        )
                    except:
                        continue

                    time_diff = (event_time - now).total_seconds()

                    # 🔔 PRE ALERT (1h vorher)
                    if 0 < time_diff <= 3600 and title not in pre_alerted_events:
                        channel = client.get_channel(CHANNEL_ID)
                        if channel:
                            await channel.send(
                                f"⚠️ Upcoming News:\n📊 {title}\n⏰ in weniger als 1 Stunde"
                            )
                            print(f"🔔 Pre-Alert: {title}", flush=True)
                            pre_alerted_events.add(title)

                    # 📊 RELEASE POST
                    if actual and title not in posted_events:
                        channel = client.get_channel(CHANNEL_ID)
                        if channel:
                            msg = f"📊 {title}\nActual: {actual}"
                            await channel.send(msg)
                            print(f"📤 Gesendet: {title}", flush=True)
                            posted_events.add(title)

                except Exception as e:
                    print(f"❌ Fehler im Event Loop: {e}", flush=True)

        except Exception as e:
            print(f"❌ Loop Fehler: {e}", flush=True)

        await asyncio.sleep(60)


@client.event
async def on_ready():
    print(f"🤖 Eingeloggt als {client.user}", flush=True)
    client.loop.create_task(news_loop())


client.run(TOKEN)
