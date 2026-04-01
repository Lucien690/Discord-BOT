import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import os
import sys

# 🔥 sofort Logs
sys.stdout.reconfigure(line_buffering=True)

print("🚀 SCRIPT STARTET", flush=True)

# 🔐 ENV
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# Discord Setup
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Speicher
sent_events = set()
pre_alerts_1h = set()
pre_alerts_30m = set()

# 🔥 EVENTS LADEN
def get_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        if not response.content or b"<" not in response.content:
            print("❌ Kein gültiges XML", flush=True)
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"❌ XML kaputt → skip: {e}", flush=True)
            return []

        events = []

        for event in root.findall("event"):
            title = event.findtext("title", default="N/A")
            country = event.findtext("country", default="N/A")
            date = event.findtext("date", default="")
            time_ = event.findtext("time", default="")

            impact = event.findtext("impact", default="low").lower()
            if impact not in ["high", "3", "medium"]:
                continue

            actual = event.findtext("actual", default="")
            forecast = event.findtext("forecast", default="")
            previous = event.findtext("previous", default="")

            events.append({
                "title": title,
                "country": country,
                "date": date,
                "time": time_,
                "impact": impact,
                "actual": actual,
                "forecast": forecast,
                "previous": previous
            })

        print(f"✅ {len(events)} Events geladen", flush=True)
        return events

    except Exception as e:
        print(f"❌ Fehler beim Laden: {e}", flush=True)
        return []

# 🔁 LOOP
async def news_loop():
    await client.wait_until_ready()

    print("🟢 Bot ist ready → starte Loop", flush=True)

    while not client.is_closed():
        try:
            now = datetime.now(timezone.utc) + timedelta(hours=2)
            print(f"⏰ Check um {now}", flush=True)

            channel = client.get_channel(CHANNEL_ID)
            if channel is None:
                print("❌ Channel nicht gefunden!", flush=True)
                await asyncio.sleep(60)
                continue

            events = get_events()

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
                    )
                except:
                    continue

                key = f"{title}_{date}_{time_}"
                time_diff = (event_time - now).total_seconds()

                # 💱 Paare
                pairs = ""
                if "USD" in country:
                    pairs = "EUR/USD, GBP/USD, XAU/USD"
                elif "EUR" in country:
                    pairs = "EUR/USD, EUR/JPY"
                elif "GBP" in country:
                    pairs = "GBP/USD, GBP/JPY"

                forecast = event.get("forecast", "")
                previous = event.get("previous", "")
                actual = event.get("actual", "")

                # 🔔 1h Alert
                if 3300 <= time_diff <= 3900:
                    if key not in pre_alerts_1h:
                        msg = (
                            f"🔔 **{country} - {title} ({time_})**\n\n"
                            f"Forecast: {forecast}\n"
                            f"Previous: {previous}\n\n"
                            f"➡️ Erwartung: Wichtiges Event 🚨\n"
                            f"💱 Paare: {pairs}"
                        )
                        await channel.send(msg)
                        print(f"🔔 1H Alert: {title}", flush=True)
                        pre_alerts_1h.add(key)

                # ⏳ 30m Alert
                if 1500 <= time_diff <= 2100:
                    if key not in pre_alerts_30m:
                        msg = (
                            f"⏳ **{country} - {title} ({time_})**\n\n"
                            f"Forecast: {forecast}\n"
                            f"Previous: {previous}\n\n"
                            f"⚠️ Event steht kurz bevor\n"
                            f"💱 Paare: {pairs}"
                        )
                        await channel.send(msg)
                        print(f"⏳ 30M Alert: {title}", flush=True)
                        pre_alerts_30m.add(key)

                # 📊 EVENT
                if 0 < time_diff <= 300:
                    if key not in sent_events:

                        analysis = "Neutral"

                        try:
                            a = float(actual.replace("%","").replace(",",".")) if actual else None
                            f = float(forecast.replace("%","").replace(",",".")) if forecast else None

                            if a is not None and f is not None:
                                if a > f:
                                    analysis = "Bullish 📈"
                                elif a < f:
                                    analysis = "Bearish 📉"
                        except:
                            pass

                        msg = (
                            f"📊 **{country} - {title}**\n\n"
                            f"Actual: {actual}\n"
                            f"Forecast: {forecast}\n"
                            f"Previous: {previous}\n\n"
                            f"➡️ Analyse: {analysis}\n"
                            f"💱 Paare: {pairs}"
                        )

                        await channel.send(msg)
                        print(f"📤 Event gesendet: {title}", flush=True)
                        sent_events.add(key)

        except Exception as e:
            print(f"❌ Loop Fehler: {e}", flush=True)

        await asyncio.sleep(60)

# 🚀 START
@client.event
async def on_ready():
    print(f"🤖 Eingeloggt als {client.user}", flush=True)
    client.loop.create_task(news_loop())

# 💬 TEST COMMAND
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions and "test" in message.content.lower():
        await message.channel.send("✅ Bot funktioniert!")
        print("💬 Test Antwort gesendet", flush=True)

client.run(TOKEN)
