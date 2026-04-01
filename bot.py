import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import sys
from dateutil import parser

sys.stdout.reconfigure(line_buffering=True)
print("🚀 SCRIPT STARTET", flush=True)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

sent_events = set()
pre_alerts_1h = set()
pre_alerts_30m = set()
last_events = []
loop_started = False

# =========================
# 📊 MARKETS
# =========================
def get_pairs(country, title=""):
    pairs_map = {
        "USD": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "USOIL", "US30", "NAS100"],
        "EUR": ["EUR/USD", "EUR/JPY", "EUR/GBP"],
        "GBP": ["GBP/USD", "GBP/JPY", "EUR/GBP"],
        "JPY": ["USD/JPY", "EUR/JPY", "GBP/JPY"],
    }

    pairs = pairs_map.get(country, [f"{country} Pairs"])

    if any(word in title.lower() for word in ["crypto", "btc", "bitcoin"]):
        pairs.append("BTC")

    return ", ".join(pairs)

# =========================
# 📡 EVENTS
# =========================
def get_events():
    global last_events

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        try:
            root = ET.fromstring(response.content)
        except:
            print("❌ XML kaputt → Cache", flush=True)
            return last_events

        events = []

        for event in root.findall("event"):
            events.append({
                "title": event.findtext("title", "N/A"),
                "country": event.findtext("country", "N/A"),
                "date": event.findtext("date", ""),
                "time": event.findtext("time", ""),
                "impact": event.findtext("impact", "low").lower(),
                "actual": event.findtext("actual", "N/A"),
                "forecast": event.findtext("forecast", "N/A"),
                "previous": event.findtext("previous", "N/A")
            })

        last_events = events
        return events

    except:
        return last_events

# =========================
# 🔁 LOOP
# =========================
async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    while not client.is_closed():
        now = datetime.now() + timedelta(hours=2)
        events = get_events()

        for event in events:
            try:
                event_time = parser.parse(f"{event['date']} {event['time']}") + timedelta(hours=2)
            except:
                continue

            diff = (event_time - now).total_seconds()
            key = f"{event['title']}_{event['date']}_{event['time']}"

            if 0 < diff <= 300 and key not in sent_events:

                actual = event["actual"]
                forecast = event["forecast"]

                analysis = "Keine Daten"
                risk = "⚖️ Neutral"
                explanation = "➡️ Märkte seitwärts"

                try:
                    a = float(actual.replace("K", "000"))
                    f = float(forecast.replace("K", "000"))

                    diff_value = a - f
                    diff_percent = abs(diff_value) / f if f != 0 else 0

                    if diff_value > 0:
                        strength = "leicht besser"
                        if diff_percent > 0.2:
                            strength = "deutlich stärker"
                        elif diff_percent > 0.05:
                            strength = "spürbar besser"

                        analysis = f"📈 {strength} als erwartet → bullish"
                        risk = "🟢 Risk-On"
                        explanation = "📈 NAS100 ↑ | 🟡 Gold ↓ | 🛢️ Öl ↑ | ₿ BTC ↑"

                    elif diff_value < 0:
                        strength = "leicht schlechter"
                        if diff_percent > 0.2:
                            strength = "deutlich schlechter"
                        elif diff_percent > 0.05:
                            strength = "spürbar schlechter"

                        analysis = f"📉 {strength} als erwartet → bearish"
                        risk = "🔴 Risk-Off"
                        explanation = "📉 NAS100 ↓ | 🟡 Gold ↑ | 🛢️ Öl ↓ | ₿ BTC ↓"

                except:
                    pass

                embed = discord.Embed(
                    title=f"📊 {event['country']} - {event['title']}",
                    description="Event läuft jetzt!",
                    color=0xff0000
                )

                embed.add_field(name="📈 Actual", value=actual)
                embed.add_field(name="📊 Forecast", value=forecast)
                embed.add_field(name="📉 Previous", value=event["previous"])

                embed.add_field(name="🧠 Analyse", value=analysis, inline=False)
                embed.add_field(name="🌍 Markt", value=f"{risk}\n{explanation}", inline=False)
                embed.add_field(name="💱 Märkte", value=get_pairs(event["country"], event["title"]), inline=False)

                await channel.send("@HIGH IMPACT", embed=embed)
                sent_events.add(key)

        await asyncio.sleep(60)

# =========================
# 🧪 COMMANDS
# =========================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.lower() == "!force news":

        country = "USD"
        title = "Test Event"

        actual = "250K"
        forecast = "180K"
        previous = "170K"

        # 🔔 1H
        await message.channel.send("🔔 Event in 1 Stunde")
        await asyncio.sleep(1)

        # ⏳ 30M
        await message.channel.send("⏳ Event in 30 Minuten")
        await asyncio.sleep(1)

        # 📊 LIVE
        embed = discord.Embed(
            title=f"📊 {country} - {title}",
            description="Event läuft jetzt!",
            color=0xff0000
        )

        embed.add_field(name="📈 Actual", value=actual)
        embed.add_field(name="📊 Forecast", value=forecast)
        embed.add_field(name="📉 Previous", value=previous)

        embed.add_field(name="🧠 Analyse", value="📈 besser → bullish", inline=False)
        embed.add_field(name="🌍 Markt", value="🟢 Risk-On\n📈 NAS100 ↑ | 🟡 Gold ↓", inline=False)
        embed.add_field(name="💱 Märkte", value="EUR/USD, NAS100, GOLD", inline=False)

        await message.channel.send("@HIGH IMPACT", embed=embed)

# =========================
# 🚀 START
# =========================
@client.event
async def on_ready():
    global loop_started

    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True

client.run(TOKEN)
