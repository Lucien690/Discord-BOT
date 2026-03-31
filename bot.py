import discord
import requests
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1475125646064619541

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

sent_reminders = set()
sent_releases = set()


# 🔥 SAFE XML READER (FIX)
def safe_find(event, tag):
    found = event.find(tag)
    return found.text if found is not None else ""


def get_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    response = requests.get(url)

    root = ET.fromstring(response.content)
    events = []

    for event in root.findall("event"):
        title = safe_find(event, "title")
        country = safe_find(event, "country")
        impact = safe_find(event, "impact")
        date = safe_find(event, "date")
        time = safe_find(event, "time")
        forecast = safe_find(event, "forecast")
        previous = safe_find(event, "previous")
        actual = safe_find(event, "actual")

        if impact not in ["High", "Medium"]:
            continue

        if time in ["All Day", "Tentative"]:
            continue

        try:
            event_time = datetime.strptime(f"{date} {time}", "%Y.%m.%d %H:%M")
        except:
            continue

        events.append({
            "title": title,
            "country": country,
            "impact": impact,
            "time": event_time,
            "forecast": forecast,
            "previous": previous,
            "actual": actual
        })

    return events


def analyze(actual, forecast):
    try:
        actual_val = float(actual.replace("%", "").replace("M", ""))
        forecast_val = float(forecast.replace("%", "").replace("M", ""))
    except:
        return "⚠️ Keine klare Analyse möglich"

    if actual_val > forecast_val:
        return "📈 BULLISH"
    elif actual_val < forecast_val:
        return "📉 BEARISH"
    else:
        return "⚖️ NEUTRAL"


async def news_loop():
    await client.wait_until_ready()
    channel = await client.fetch_channel(CHANNEL_ID)

    while not client.is_closed():
        now = datetime.utcnow() + timedelta(hours=2)

        events = get_events()

        for event in events:
            key = event["title"] + str(event["time"])
            time_diff = (event["time"] - now).total_seconds()

            print("EVENT:", event["title"], "| ACTUAL:", event["actual"])

            # ⏰ Reminder 1h vorher
            if 3500 < time_diff < 3700 and key not in sent_reminders:
                embed = discord.Embed(
                    title="⏰ UPCOMING EVENT",
                    description=f"{event['country']} - {event['title']}",
                    color=discord.Color.orange()
                )
                embed.add_field(name="📊 Impact", value=event["impact"])
                embed.add_field(name="🕐 Zeit", value=str(event["time"]))

                await channel.send(embed=embed)
                sent_reminders.add(key)

            # 🚨 Release
            if event["actual"] != "" and key not in sent_releases:
                print("SENDING:", event["title"])

                result = analyze(event["actual"], event["forecast"])

                embed = discord.Embed(
                    title="🚨 ECONOMIC RELEASE",
                    description=f"{event['country']} - {event['title']}",
                    color=discord.Color.red()
                )

                embed.add_field(name="📊 Actual", value=event["actual"], inline=True)
                embed.add_field(name="📉 Forecast", value=event["forecast"], inline=True)
                embed.add_field(name="📈 Previous", value=event["previous"], inline=True)
                embed.add_field(name="🔥 Ergebnis", value=result, inline=False)

                await channel.send(content="@everyone 🚨", embed=embed)
                sent_releases.add(key)

        await asyncio.sleep(60)


@client.event
async def on_ready():
    print("FOREX BOT ONLINE")
    client.loop.create_task(news_loop())


# ✅ TEST MIT @BOT
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        if "test" in message.content.lower():
            await message.channel.send("Bot funktioniert ✅")


client.run(TOKEN)
