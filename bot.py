import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import os
import sys
from bs4 import BeautifulSoup

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
    pairs_map = {
        "USD": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "USOIL", "US30", "NAS100"],
        "EUR": ["EUR/USD", "EUR/JPY", "EUR/GBP"],
        "GBP": ["GBP/USD", "GBP/JPY", "EUR/GBP"],
        "JPY": ["USD/JPY", "EUR/JPY", "GBP/JPY"],
        "CHF": ["USD/CHF", "EUR/CHF", "CHF/JPY"],
        "NZD": ["NZD/USD", "AUD/NZD", "NZD/JPY"],
        "AUD": ["AUD/USD", "AUD/JPY", "AUD/NZD"],
        "CAD": ["USD/CAD", "CAD/JPY", "EUR/CAD", "USOIL"]
    }

    pairs = pairs_map.get(country, [f"{country} Pairs"])

    title_lower = title.lower()
    crypto_keywords = ["crypto", "bitcoin", "btc", "blockchain", "sec"]

    if any(word in title_lower for word in crypto_keywords):
        pairs.append("BTC")

    return ", ".join(pairs)

def get_events():
    global last_events

    try:
        url = "https://www.forexfactory.com/calendar"
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(url, headers=headers, timeout=10).text

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr", class_="calendar__row")

        events = []
        current_date = datetime.now().strftime("%Y-%m-%d")

        for row in rows:
            try:
                time_ = row.find("td", class_="calendar__time").text.strip()
                currency = row.find("td", class_="calendar__currency").text.strip()
                title = row.find("td", class_="calendar__event").text.strip()

                impact = "low"
                impact_span = row.find("span", class_="impact")
                if impact_span:
                    classes = impact_span.get("class", [])
                    if "high" in classes:
                        impact = "high"
                    elif "medium" in classes:
                        impact = "medium"

                actual = row.find("td", class_="calendar__actual").text.strip()
                forecast = row.find("td", class_="calendar__forecast").text.strip()
                previous = row.find("td", class_="calendar__previous").text.strip()

                if not time_ or time_.lower() in ["all day", "tentative"]:
                    continue

                events.append({
                    "title": title,
                    "country": currency,
                    "date": current_date,
                    "time": time_,
                    "impact": impact,
                    "actual": actual if actual else "N/A",
                    "forecast": forecast if forecast else "N/A",
                    "previous": previous if previous else "N/A"
                })

            except:
                continue

        print(f"✅ {len(events)} Events (Scraping)", flush=True)
        last_events = events
        return events

    except Exception as e:
        print(f"❌ Scraping Fehler → nutze Cache: {e}", flush=True)
        return last_events

async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    print("🟢 Bot ist ready → starte Loop", flush=True)

    while not client.is_closed():
        try:
            # ✅ FIX: lokale Zeit
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

                if time_ == "All Day" or time_ == "":
                    continue

                try:
                    # ✅ FIX: keine Zeitzone mehr
                    event_time = datetime.strptime(
                        f"{date} {time_}", "%Y-%m-%d %H:%M"
                    )
                except:
                    continue

                key = f"{title}_{date}_{time_}"
                diff = (event_time - now).total_seconds()

                color = 0xff0000 if impact in ["high", "3"] else 0xffcc00
                mention = "@HIGH IMPACT" if impact in ["high", "3"] else None

                if 0 < diff <= 3900:
                    if key not in pre_alerts_1h:
                        embed = discord.Embed(
                            title=f"🔔 {country} - {title}",
                            description="Event in 1 Stunde",
                            color=color
                        )
                        embed.add_field(name="⏰ Zeit", value=time_, inline=True)
                        embed.add_field(name="📊 Impact", value=impact.upper(), inline=True)

                        await channel.send(content=mention, embed=embed)
                        print(f"🔔 1h Alert: {title}", flush=True)
                        pre_alerts_1h.add(key)

                if 0 < diff <= 2100:
                    if key not in pre_alerts_30m:
                        embed = discord.Embed(
                            title=f"⏳ {country} - {title}",
                            description="Event in 30 Minuten",
                            color=color
                        )
                        embed.add_field(name="⏰ Zeit", value=time_, inline=True)
                        embed.add_field(name="📊 Impact", value=impact.upper(), inline=True)

                        await channel.send(content=mention, embed=embed)
                        print(f"⏳ 30m Alert: {title}", flush=True)
                        pre_alerts_30m.add(key)

                if 0 < diff <= 300:
                    if key not in sent_events:

                        if impact in ["high", "3"]:
                            risk = "🔴 Risk-Off"
                            explanation = "📉 NAS100 ↓ | 🟡 Gold ↑ | 🛢️ Öl ↓ | ₿ BTC ↓"
                        elif impact == "medium":
                            risk = "🟢 Risk-On"
                            explanation = "📈 NAS100 ↑ | 🟡 Gold ↓ | 🛢️ Öl ↑ | ₿ BTC ↑"
                        else:
                            risk = "⚖️ Neutral"
                            explanation = "➡️ NAS100 ↔ | 🟡 Gold ↔ | 🛢️ Öl ↔ | ₿ BTC ↔"

                        analysis = "Keine Daten"
                        try:
                            a = float(actual.replace("%", "").replace("K", "000"))
                            f = float(forecast.replace("%", "").replace("K", "000"))

                            if a > f:
                                analysis = "📈 Besser als erwartet → bullish"
                            elif a < f:
                                analysis = "📉 Schlechter als erwartet → bearish"
                            else:
                                analysis = "➡️ Wie erwartet → neutral"
                        except:
                            pass

                        embed = discord.Embed(
                            title=f"📊 {country} - {title}",
                            description="Event läuft jetzt!",
                            color=color
                        )

                        embed.add_field(name="⏰ Zeit", value=time_, inline=True)
                        embed.add_field(name="📊 Impact", value=impact.upper(), inline=True)

                        embed.add_field(name="📈 Actual", value=actual, inline=True)
                        embed.add_field(name="📊 Forecast", value=forecast, inline=True)
                        embed.add_field(name="📉 Previous", value=previous, inline=True)

                        embed.add_field(name="🧠 Analyse", value=analysis, inline=False)

                        embed.add_field(
                            name="🌍 Marktstimmung",
                            value=f"{risk}\n{explanation}",
                            inline=False
                        )

                        embed.add_field(
                            name="💱 Betroffene Märkte",
                            value=get_pairs(country, title),
                            inline=False
                        )

                        await channel.send(content=mention, embed=embed)
                        print(f"📤 Event gesendet: {title}", flush=True)
                        sent_events.add(key)

        except Exception as e:
            print(f"❌ Loop Fehler: {e}", flush=True)

        await asyncio.sleep(60)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if "test" in message.content.lower():
        await message.channel.send("✅ Bot funktioniert!")
        print("💬 Test Antwort gesendet", flush=True)

    if message.content.lower() == "!force news":
        embed = discord.Embed(
            title="📊 USD - Test Event",
            description="Manuell ausgelöst",
            color=0xff0000
        )

        embed.add_field(name="⏰ Zeit", value="JETZT", inline=True)
        embed.add_field(name="📊 Impact", value="HIGH", inline=True)

        embed.add_field(name="📈 Actual", value="250K", inline=True)
        embed.add_field(name="📊 Forecast", value="180K", inline=True)
        embed.add_field(name="📉 Previous", value="170K", inline=True)

        embed.add_field(
            name="🧠 Analyse",
            value="📈 Besser als erwartet → bullish",
            inline=False
        )

        embed.add_field(
            name="🌍 Marktstimmung",
            value="🔴 Risk-Off\n📉 NAS100 ↓ | 🟡 Gold ↑ | 🛢️ Öl ↓ | ₿ BTC ↓",
            inline=False
        )

        embed.add_field(
            name="💱 Betroffene Märkte",
            value="EUR/USD, GBP/USD, USD/JPY, XAU/USD, USOIL, US30, NAS100",
            inline=False
        )

        await message.channel.send(content="@HIGH IMPACT", embed=embed)
        print("🧪 Test News gesendet", flush=True)

@client.event
async def on_ready():
    global loop_started

    print(f"🤖 Eingeloggt als {client.user}", flush=True)

    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True

client.run(TOKEN)
