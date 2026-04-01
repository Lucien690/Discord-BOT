import discord
import asyncio
import requests
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

    url = "https://calendar.fxstreet.com/v1/eventDates"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        events = []

        for event in data:
            title = event.get("event", "N/A")
            country = event.get("countryCode", "N/A")
            time_raw = event.get("date", "")
            impact = str(event.get("importance", "1"))

            actual = event.get("actual", "N/A")
            forecast = event.get("forecast", "N/A")
            previous = event.get("previous", "N/A")

            if impact not in ["2", "3"]:
                continue

            try:
                dt = datetime.fromisoformat(time_raw.replace("Z", ""))
                date = dt.strftime("%Y-%m-%d")
                time_ = dt.strftime("%H:%M")
            except:
                continue

            events.append({
                "title": title,
                "country": country,
                "date": date,
                "time": time_,
                "impact": impact,
                "actual": actual if actual else "N/A",
                "forecast": forecast if forecast else "N/A",
                "previous": previous if previous else "N/A"
            })

        print(f"✅ {len(events)} Events geladen (FXStreet)", flush=True)

        last_events = events
        return events

    except Exception as e:
        print(f"❌ FXStreet Fehler → Cache: {e}", flush=True)
        return last_events

async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    print("🟢 Bot ist ready → starte Loop", flush=True)

    while not client.is_closed():
        try:
            now = datetime.now()
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

                try:
                    event_time = parser.parse(f"{date} {time_}")
                except:
                    continue

                key = f"{title}_{date}_{time_}"
                diff = (event_time - now).total_seconds()

                mention = "@HIGH IMPACT" if impact == "3" else "@IMPACT"

                # 🔔 1H ALERT
                if 3500 < diff < 3700:
                    if key not in pre_alerts_1h:
                        embed = discord.Embed(
                            title=f"🔔 {country} - {title}",
                            description="Event in 1 Stunde",
                            color=0xff0000
                        )
                        await channel.send(content=mention, embed=embed)
                        pre_alerts_1h.add(key)

                # ⏳ 30M ALERT
                if 1700 < diff < 1900:
                    if key not in pre_alerts_30m:
                        embed = discord.Embed(
                            title=f"⏳ {country} - {title}",
                            description="Event in 30 Minuten",
                            color=0xffcc00
                        )
                        await channel.send(content=mention, embed=embed)
                        pre_alerts_30m.add(key)

                # 📊 LIVE EVENT
                if 0 < diff < 120:
                    if key not in sent_events:

                        analysis = "Keine Daten"
                        meaning = ""
                        reaction = ""

                        try:
                            a = float(actual.replace("K","000").replace("%",""))
                            f = float(forecast.replace("K","000").replace("%",""))

                            if a > f:
                                analysis = f"Die Daten ({actual}) sind besser als erwartet ({forecast}). Die Wirtschaft ist stärker."
                                meaning = "→ Wachstum steigt\n→ Konsum steigt\n→ Vertrauen steigt"
                                reaction = "📈 NAS100 & US30 steigen\n🛢️ Öl steigt\n₿ BTC steigt\n🟡 Gold fällt"

                            elif a < f:
                                analysis = f"Die Daten ({actual}) sind schlechter als erwartet ({forecast}). Die Wirtschaft schwächelt."
                                meaning = "→ Wachstum sinkt\n→ Unsicherheit steigt\n→ Investoren vorsichtig"
                                reaction = "📉 NAS100 & US30 fallen\n🟡 Gold steigt\n₿ BTC fällt\n🛢️ Öl fällt"

                            else:
                                analysis = "Die Daten entsprechen der Erwartung."
                                meaning = "→ Keine Überraschung\n→ Markt stabil"
                                reaction = "➡️ Kaum Bewegung"

                        except:
                            pass

                        embed = discord.Embed(
                            title=f"📊 {country} - {title}",
                            description="Event läuft jetzt!",
                            color=0xff0000
                        )

                        embed.add_field(name="📈 Actual", value=actual, inline=True)
                        embed.add_field(name="📊 Forecast", value=forecast, inline=True)
                        embed.add_field(name="📉 Previous", value=previous, inline=True)

                        embed.add_field(name="🧠 Analyse", value=analysis, inline=False)
                        embed.add_field(name="💡 Bedeutung", value=meaning, inline=False)
                        embed.add_field(name="🌍 Marktreaktion", value=reaction, inline=False)

                        embed.add_field(
                            name="💱 Märkte",
                            value=get_pairs(country, title),
                            inline=False
                        )

                        await channel.send(content=mention, embed=embed)
                        sent_events.add(key)

        except Exception as e:
            print(f"❌ Loop Fehler: {e}", flush=True)

        await asyncio.sleep(60)

# 🧪 TEST COMMAND (JETZT DRIN)
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if "erstelle fake news" in message.content.lower():

        country = "USD"
        title = "Fake Event"

        actual = "250K"
        forecast = "180K"
        previous = "170K"

        mention = "@HIGH IMPACT"

        analysis = "Keine Daten"
        meaning = ""
        reaction = ""

        try:
            a = float(actual.replace("K","000").replace("%",""))
            f = float(forecast.replace("K","000").replace("%",""))

            if a > f:
                analysis = f"Die Daten ({actual}) sind besser als erwartet ({forecast}). Die Wirtschaft ist stärker."
                meaning = "→ Wachstum steigt\n→ Konsum steigt\n→ Vertrauen steigt"
                reaction = "📈 NAS100 & US30 steigen\n🛢️ Öl steigt\n₿ BTC steigt\n🟡 Gold fällt"

            elif a < f:
                analysis = f"Die Daten ({actual}) sind schlechter als erwartet ({forecast}). Die Wirtschaft schwächelt."
                meaning = "→ Wachstum sinkt\n→ Unsicherheit steigt\n→ Investoren vorsichtig"
                reaction = "📉 NAS100 & US30 fallen\n🟡 Gold steigt\n₿ BTC fällt\n🛢️ Öl fällt"

            else:
                analysis = "Die Daten entsprechen der Erwartung."
                meaning = "→ Keine Überraschung\n→ Markt stabil"
                reaction = "➡️ Kaum Bewegung"

        except:
            pass

        embed = discord.Embed(
            title=f"📊 {country} - {title}",
            description="TEST EVENT",
            color=0xff0000
        )

        embed.add_field(name="📈 Actual", value=actual, inline=True)
        embed.add_field(name="📊 Forecast", value=forecast, inline=True)
        embed.add_field(name="📉 Previous", value=previous, inline=True)

        embed.add_field(name="🧠 Analyse", value=analysis, inline=False)
        embed.add_field(name="💡 Bedeutung", value=meaning, inline=False)
        embed.add_field(name="🌍 Marktreaktion", value=reaction, inline=False)

        embed.add_field(
            name="💱 Märkte",
            value=get_pairs(country, title),
            inline=False
        )

        await message.channel.send(content=mention, embed=embed)

@client.event
async def on_ready():
    global loop_started

    print(f"🤖 Eingeloggt als {client.user}", flush=True)

    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True

client.run(TOKEN)
