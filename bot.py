import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
from dateutil import parser

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

sent_events = set()
alerted_events = set()
cache = []

# =========================
# 📊 MÄRKTE
# =========================
def get_markets():
    return "NAS100, US30, XAUUSD, USOIL, BTC"

# =========================
# 🧠 ANALYSE (VERBESSERT)
# =========================
def analyze(actual, forecast):
    try:
        a = float(actual.replace("K","000").replace("%",""))
        f = float(forecast.replace("K","000").replace("%",""))

        diff = a - f
        diff_percent = abs(diff) / f if f != 0 else 0

        # 📈 POSITIV
        if diff > 0:

            if diff_percent > 0.2:
                strength = "stark besser als erwartet"
                market = "📈 Starke Bewegung nach oben wahrscheinlich"
            elif diff_percent > 0.05:
                strength = "spürbar besser als erwartet"
                market = "📈 Märkte steigen moderat"
            else:
                strength = "leicht besser als erwartet"
                market = "📈 Kleine Aufwärtsbewegung"

            analysis = f"📈 {strength}"
            meaning = "Die Wirtschaft zeigt Stärke → Investoren kaufen riskante Assets"
            reaction = f"🟢 Risk-On\n{market}"

        # 📉 NEGATIV
        elif diff < 0:

            if diff_percent > 0.2:
                strength = "deutlich schlechter als erwartet"
                market = "📉 Starke Abverkäufe möglich"
            elif diff_percent > 0.05:
                strength = "spürbar schlechter als erwartet"
                market = "📉 Märkte fallen moderat"
            else:
                strength = "leicht schlechter als erwartet"
                market = "📉 Kleine Abwärtsbewegung"

            analysis = f"📉 {strength}"
            meaning = "Die Wirtschaft schwächelt → Unsicherheit steigt"
            reaction = f"🔴 Risk-Off\n{market}"

        # ➡️ NEUTRAL
        else:
            analysis = "➡️ Wie erwartet"
            meaning = "Keine Überraschung → Markt bleibt stabil"
            reaction = "⚖️ Neutral\nKaum Bewegung"

        return analysis, meaning, reaction

    except:
        return (
            "Keine Daten",
            "Daten konnten nicht ausgewertet werden",
            "Keine klare Marktreaktion"
        )

# =========================
# 📡 EVENTS LADEN
# =========================
def get_events():
    global cache
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        r = requests.get(url, timeout=10)
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
        print(f"✅ {len(events)} Events geladen")
        return events

    except Exception as e:
        print(f"❌ XML Fehler → Cache genutzt: {e}")
        return cache

# =========================
# 🔁 LOOP
# =========================
async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    print("🚀 Bot läuft...")

    while True:
        try:
            now = datetime.now() + timedelta(hours=2)
            events = get_events()

            for e in events:
                try:
                    event_time = parser.parse(f"{e['date']} {e['time']}") + timedelta(hours=2)
                except:
                    continue

                diff = (event_time - now).total_seconds()
                key = f"{e['title']}_{e['date']}_{e['time']}"

                # 🔔 1H ALERT
                if 3500 < diff < 3700 and key not in alerted_events:

                    tag = "@HIGH IMPACT" if e["impact"] in ["high","3"] else "@IMPACT"

                    msg = f"""{tag}

🔔 Heute wichtige News

📊 {e['country']} - {e['title']}
⏰ {e['time']}
"""

                    await channel.send(msg)
                    alerted_events.add(key)

                # 📊 LIVE EVENT
                if 0 < diff < 120 and key not in sent_events:

                    tag = "@HIGH IMPACT" if e["impact"] in ["high","3"] else "@IMPACT"

                    analysis, meaning, reaction = analyze(e["actual"], e["forecast"])

                    msg = f"""{tag}

📊 {e['country']} - {e['title']}

📈 Actual: {e['actual']}
📊 Forecast: {e['forecast']}
📉 Previous: {e['previous']}

🧠 Analyse:
{analysis}

💡 Bedeutung:
{meaning}

🌍 Marktreaktion:
{reaction}

💱 Betroffene Märkte:
{get_markets()}
"""

                    await channel.send(msg)
                    sent_events.add(key)

        except Exception as e:
            print(f"❌ Loop Fehler: {e}")

        await asyncio.sleep(60)

# =========================
# 🧪 TEST COMMAND
# =========================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.lower() == "@forex bot erstelle fake news":

        analysis, meaning, reaction = analyze("250K", "180K")

        msg = f"""@HIGH IMPACT

📊 USD - Fake News Event

📈 Actual: 250K
📊 Forecast: 180K
📉 Previous: 170K

🧠 Analyse:
{analysis}

💡 Bedeutung:
{meaning}

🌍 Marktreaktion:
{reaction}

💱 Betroffene Märkte:
{get_markets()}
"""

        await message.channel.send(msg)

# =========================
# 🚀 START
# =========================
@client.event
async def on_ready():
    print(f"🤖 Eingeloggt als {client.user}")
    client.loop.create_task(news_loop())

client.run(TOKEN)
