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

def get_pairs(country, title=""):
    return "NAS100, US30, XAUUSD, USOIL, BTC"

def get_events():
    global last_events

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=10)

        if not response.content or b"<" not in response.content:
            print("❌ Kein gültiges XML → Cache", flush=True)
            return last_events

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"❌ XML kaputt → Cache: {e}", flush=True)
            return last_events

        events = []

        for event in root.findall("event"):
            title = event.findtext("title", "N/A")
            country = event.findtext("country", "N/A")
            date = event.findtext("date", "")
            time_ = event.findtext("time", "")
            impact = event.findtext("impact", "low").lower()

            actual = event.findtext("actual", "N/A")
            forecast = event.findtext("forecast", "N/A")
            previous = event.findtext("previous", "N/A")

            # ✅ HIGH + MEDIUM + LOW
            if impact not in ["high", "3", "medium", "low", "1"]:
                continue

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

        print(f"✅ {len(events)} Events geladen (XML)", flush=True)

        last_events = events
        return events

    except Exception as e:
        print(f"❌ Fehler → Cache: {e}", flush=True)
        return last_events

async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    print("🟢 Bot ist ready → starte Loop", flush=True)

    while not client.is_closed():
        try:
            now = datetime.now() + timedelta(hours=2)
            print(f"⏰ Check um {now}", flush=True)

            events = get_events()

            for event in events:
                title = event["title"]
                country = event["country"]
                date = event["date"]
                time_ = event["time"]
                impact = event["impact"]

                actual = event["actual"]
                forecast = event["forecast"]
                previous = event["previous"]

                if time_ == "" or time_ == "All Day":
                    continue

                try:
                    event_time = parser.parse(f"{date} {time_}") + timedelta(hours=2)
                except:
                    continue

                key = f"{title}_{date}_{time_}"
                diff = (event_time - now).total_seconds()

                # ✅ TAG SYSTEM
                if impact in ["high", "3"]:
                    mention = "@HIGH IMPACT"
                    color = 0xff0000
                elif impact == "medium":
                    mention = "@IMPACT"
                    color = 0xffcc00
                else:
                    mention = "@LOW IMPACT"
                    color = 0x00ff00

                # 🔔 1H ALERT
                if 3500 < diff < 3700 and key not in pre_alerts_1h:
                    embed = discord.Embed(
                        title=f"🔔 {country} - {title}",
                        description="Event in 1 Stunde",
                        color=color
                    )
                    await channel.send(content=mention, embed=embed)
                    pre_alerts_1h.add(key)

                # ⏳ 30M ALERT
                if 1700 < diff < 1900 and key not in pre_alerts_30m:
                    embed = discord.Embed(
                        title=f"⏳ {country} - {title}",
                        description="Event in 30 Minuten",
                        color=color
                    )
                    await channel.send(content=mention, embed=embed)
                    pre_alerts_30m.add(key)

                # 📊 LIVE EVENT
                if 0 < diff < 120 and key not in sent_events:

                    analysis = ""
                    meaning = ""
                    reaction = ""

                    try:
                        a = float(actual.replace("K","000").replace("%",""))
                        f = float(forecast.replace("K","000").replace("%",""))

                        if a > f:
                            analysis = f"Die Daten ({actual}) liegen über der Erwartung ({forecast}). Die Wirtschaft ist stärker als erwartet."
                            meaning = "→ Unternehmen wachsen\n→ Konsum steigt\n→ Vertrauen steigt"
                            reaction = "📈 NAS100 & US30 steigen\n🛢️ Öl steigt\n₿ BTC steigt\n🟡 Gold fällt"

                        elif a < f:
                            analysis = f"Die Daten ({actual}) liegen unter der Erwartung ({forecast}). Die Wirtschaft ist schwächer."
                            meaning = "→ Wachstum sinkt\n→ Unsicherheit steigt\n→ Investoren vorsichtig"
                            reaction = "📉 NAS100 & US30 fallen\n🟡 Gold steigt\n₿ BTC fällt\n🛢️ Öl fällt"

                        else:
                            analysis = "Die Daten entsprechen der Erwartung."
                            meaning = "→ Keine Überraschung\n→ Markt stabil"
                            reaction = "➡️ Kaum Bewegung"

                    except:
                        analysis = "Keine Daten verfügbar"

                    embed = discord.Embed(
                        title=f"📊 {country} - {title}",
                        description="Event läuft jetzt!",
                        color=color
                    )

                    embed.add_field(name="📈 Actual", value=actual, inline=True)
                    embed.add_field(name="📊 Forecast", value=forecast, inline=True)
                    embed.add_field(name="📉 Previous", value=previous, inline=True)

                    embed.add_field(name="🧠 Analyse", value=analysis, inline=False)
                    embed.add_field(name="💡 Bedeutung", value=meaning, inline=False)
                    embed.add_field(name="🌍 Marktreaktion", value=reaction, inline=False)

                    embed.add_field(name="💱 Märkte", value=get_pairs(country, title), inline=False)

                    await channel.send(content=mention, embed=embed)
                    sent_events.add(key)

        except Exception as e:
            print(f"❌ Loop Fehler: {e}", flush=True)

        await asyncio.sleep(60)

@client.event
async def on_ready():
    global loop_started

    print(f"🤖 Eingeloggt als {client.user}", flush=True)

    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True

client.run(TOKEN)
