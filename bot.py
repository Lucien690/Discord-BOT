import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import sys
from dateutil import parser

sys.stdout.reconfigure(line_buffering=True)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

client = discord.Client(intents=discord.Intents.default())

sent_events = set()
alerted_events = set()
cache = []

# =========================
# 📊 MÄRKTE
# =========================
def get_markets():
    return "NAS100, US30, XAUUSD, USOIL, BTC"

# =========================
# 🧠 ANALYSE (EINFACH & STABIL)
# =========================
def analyze(actual, forecast):
    try:
        a = float(actual.replace("K","000").replace("%",""))
        f = float(forecast.replace("K","000").replace("%",""))

        if a > f:
            return "📈 Besser als erwartet → bullish", "🟢 Risk-On → Märkte steigen"

        elif a < f:
            return "📉 Schlechter als erwartet → bearish", "🔴 Risk-Off → Märkte fallen"

        else:
            return "➡️ Wie erwartet", "⚖️ Neutral"

    except:
        return "Keine Daten", "Keine klare Reaktion"

# =========================
# 📡 EVENTS LADEN (WIE FRÜHER + CACHE)
# =========================
def get_events():
    global cache
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        r = requests.get(url, timeout=10)

        if not r.content:
            print("❌ Kein XML → Cache", flush=True)
            return cache

        root = ET.fromstring(r.content)

        events = []
        for e in root.findall("event"):
            impact = e.findtext("impact", "").lower()

            if impact not in ["high", "medium", "3", "2"]:
                continue

            events.append({
                "title": e.findtext("title"),
                "country": e.findtext("country"),
                "date": e.findtext("date"),
                "time": e.findtext("time"),
                "impact": impact,
                "actual": e.findtext("actual", "N/A"),
                "forecast": e.findtext("forecast", "N/A"),
                "previous": e.findtext("previous", "N/A"),
            })

        cache = events
        print(f"✅ {len(events)} Events geladen", flush=True)
        return events

    except Exception as e:
        print(f"❌ XML Fehler → Cache: {e}", flush=True)
        return cache

# =========================
# 🔁 LOOP (WIE VORHER)
# =========================
async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    print("🚀 Bot läuft", flush=True)

    while True:
        now = datetime.now() + timedelta(hours=2)
        events = get_events()

        for e in events:
            try:
                event_time = parser.parse(f"{e['date']} {e['time']}") + timedelta(hours=2)
            except:
                continue

            diff = (event_time - now).total_seconds()
            key = f"{e['title']}_{e['date']}_{e['time']}"

            # 🔔 1H ALARM
            if 3500 < diff < 3700 and key not in alerted_events:

                tag = "@HIGH IMPACT" if e["impact"] in ["high","3"] else "@IMPACT"

                msg = f"""{tag}

🔔 Heute News

📊 {e['country']} - {e['title']}
⏰ {e['time']}
"""

                await channel.send(msg)
                alerted_events.add(key)

            # 📊 LIVE EVENT
            if 0 < diff < 120 and key not in sent_events:

                tag = "@HIGH IMPACT" if e["impact"] in ["high","3"] else "@IMPACT"

                analysis, reaction = analyze(e["actual"], e["forecast"])

                msg = f"""{tag}

📊 {e['country']} - {e['title']}

📈 Actual: {e['actual']}
📊 Forecast: {e['forecast']}
📉 Previous: {e['previous']}

🧠 Analyse:
{analysis}

💡 Bedeutung:
{reaction}

💱 Märkte:
{get_markets()}
"""

                await channel.send(msg)
                sent_events.add(key)

        await asyncio.sleep(60)

# =========================
# 🧪 TEST COMMAND
# =========================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.lower() == "@forex bot erstelle fake news":

        analysis, reaction = analyze("250K", "180K")

        msg = f"""@HIGH IMPACT

📊 USD - Fake Event

📈 Actual: 250K
📊 Forecast: 180K
📉 Previous: 170K

🧠 Analyse:
{analysis}

💡 Bedeutung:
{reaction}

💱 Märkte:
{get_markets()}
"""

        await message.channel.send(msg)

# =========================
# 🚀 START
# =========================
@client.event
async def on_ready():
    print(f"🤖 Eingeloggt als {client.user}", flush=True)
    client.loop.create_task(news_loop())

client.run(TOKEN)
