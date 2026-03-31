import discord
import requests
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1475125646064619541

# ✅ INTENTS
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

sent_reminders = set()
sent_releases = set()


def get_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    response = requests.get(url)

    root = ET.fromstring(response.content)
    events = []

    for event in root.findall("event"):
        title = event.find("title").text
        country = event.find("country").text
        impact = event.find("impact").text
        date = event.find("date").text
        time = event.find("time").text
        forecast = event.find("forecast").text
        previous = event.find("previous").text
        actual = event.find("actual").text

        if impact not in ["High", "Medium"]:
            continue

        if time == "All Day" or time == "Tentative":
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

            # ⏰ Reminder
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
            if event["actual"] and event["actual"].strip() != "" and key not in sent_releases:
                actual = event["actual"]
                forecast = event["forecast"]
                previous = event["previous"]

                result = analyze(actual, forecast)

                embed = discord.Embed(
                    title="🚨 ECONOMIC RELEASE",
                    description=f"{event['country']} - {event['title']}",
                    color=discord.Color.red()
                )

                embed.add_field(name="📊 Actual", value=actual, inline=True)
                embed.add_field(name="📉 Forecast", value=forecast, inline=True)
                embed.add_field(name="📈 Previous", value=previous, inline=True)
                embed.add_field(name="🔥 Ergebnis", value=result, inline=False)

                await channel.send(content="@everyone 🚨", embed=embed)
                sent_releases.add(key)

        await asyncio.sleep(60)


@client.event
async def on_ready():
    print("FOREX BOT ONLINE")
    client.loop.create_task(news_loop())


# ✅ MENTION TEST
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        if "test" in message.content.lower():
            await message.channel.send("Bot funktioniert ✅")


client.run(TOKEN)
