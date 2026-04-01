import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import sys
from dateutil import parser, tz

sys.stdout.reconfigure(line_buffering=True)

print("🚀 SCRIPT STARTET", flush=True)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# Neue Rollen-IDs (in .env eintragen!)
HIGH_ROLE_ID = int(os.getenv("HIGH_ROLE_ID", "0"))
MEDIUM_ROLE_ID = int(os.getenv("MEDIUM_ROLE_ID", "0"))
LOW_ROLE_ID = int(os.getenv("LOW_ROLE_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

sent_events = set()
pre_alerts_1h = set()
pre_alerts_30m = set()
last_events = []
loop_started = False
message_ids_to_delete = {}  # {message_id: delete_time}


def get_pairs(country: str, title: str = "") -> str:
    return "NAS100, US30, XAUUSD, USOIL, BTC"


def get_mention_and_color(impact: str):
    if impact == "high":
        return f"<@&{HIGH_ROLE_ID}>", 0xff0000
    elif impact == "medium":
        return f"<@&{MEDIUM_ROLE_ID}>", 0xffaa00
    else:
        return f"<@&{LOW_ROLE_ID}>", 0x00ff00


def get_events():
    global last_events
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content = response.content.decode("windows-1252", errors="replace")

        root = ET.fromstring(content)
        events = []

        for event in root.findall(".//event"):
            title = event.findtext("title", "N/A").strip()
            country = event.findtext("country", "N/A").strip()
            date = event.findtext("date", "").strip()
            time_str = event.findtext("time", "").strip()
            impact = event.findtext("impact", "low").lower().strip()

            actual = event.findtext("actual", "N/A")
            forecast = event.findtext("forecast", "N/A")
            previous = event.findtext("previous", "N/A")

            if impact in ["high", "3", "high impact"]:
                impact = "high"
            elif impact in ["medium", "2", "med"]:
                impact = "medium"
            elif impact in ["low", "1"]:
                impact = "low"
            else:
                continue

            if not title or time_str in ("", "All Day", "Tentative"):
                continue

            events.append({
                "title": title,
                "country": country,
                "date": date,
                "time": time_str,
                "impact": impact,
                "actual": actual,
                "forecast": forecast,
                "previous": previous
            })

        print(f"✅ {len(events)} Events geladen", flush=True)
        last_events = events
        return events

    except Exception as e:
        print(f"❌ Fehler beim Laden der Events: {e}", flush=True)
        return last_events


async def delete_old_messages(channel):
    """Löscht Nachrichten nach 24 Stunden"""
    now = datetime.utcnow()
    to_delete = []
    for msg_id, delete_time in list(message_ids_to_delete.items()):
        if now > delete_time:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
                print(f"🗑️ Nachricht {msg_id} gelöscht (24h alt)", flush=True)
            except:
                pass
            to_delete.append(msg_id)
    
    for msg_id in to_delete:
        message_ids_to_delete.pop(msg_id, None)


async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Channel nicht gefunden!", flush=True)
        return

    print(f"🟢 News-Loop gestartet im Channel: {channel.name} | Deutsche Zeit (Europe/Berlin)", flush=True)

    # Zeitzonen-Setup
    berlin_tz = tz.gettz("Europe/Berlin")
    ny_tz = tz.gettz("America/New_York")  # Events kommen meist aus NY-Zeit

    while not client.is_closed():
        try:
            now_berlin = datetime.now(berlin_tz)
            print(f"⏰ Check um {now_berlin.strftime('%Y-%m-%d %H:%M:%S')} (MEZ/MESZ)", flush=True)

            await delete_old_messages(channel)  # Alte Nachrichten aufräumen

            events = get_events()

            for event in events:
                title = event["title"]
                country = event["country"]
                date_str = event["date"]
                time_str = event["time"]
                impact = event["impact"]

                key = f"{title}_{date_str}_{time_str}"

                # Zeit parsen und in Berlin-Zeit umrechnen
                try:
                    # XML-Zeit als NY-Zeit interpretieren und nach Berlin konvertieren
                    naive_time = parser.parse(f"{date_str} {time_str}")
                    event_time_ny = naive_time.replace(tzinfo=ny_tz)
                    event_time_berlin = event_time_ny.astimezone(berlin_tz)
                except Exception:
                    continue

                diff = (event_time_berlin - now_berlin).total_seconds()

                # Alte Events aufräumen
                if diff < -7200:
                    sent_events.discard(key)
                    pre_alerts_1h.discard(key)
                    pre_alerts_30m.discard(key)
                    continue

                mention, color = get_mention_and_color(impact)

                # 1 Stunde vorher
                if 3500 < diff < 3700 and key not in pre_alerts_1h:
                    embed = discord.Embed(
                        title=f"🔔 {country} — {title}",
                        description=f"**Event in ca. 1 Stunde** (um {event_time_berlin.strftime('%H:%M')} Uhr)",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_1h.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # 30 Minuten vorher
                if 1700 < diff < 1900 and key not in pre_alerts_30m:
                    embed = discord.Embed(
                        title=f"⏳ {country} — {title}",
                        description=f"**Event in ca. 30 Minuten** (um {event_time_berlin.strftime('%H:%M')} Uhr)",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_30m.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # LIVE
                if 0 < diff < 180 and key not in sent_events:
                    # ... (der Rest des LIVE-Blocks bleibt fast gleich wie vorher)

                    is_better = False
                    diff_val = 0
                    try:
                        a_str = str(event["actual"]).replace("K", "000").replace("%", "").replace(",", "").strip()
                        f_str = str(event["forecast"]).replace("K", "000").replace("%", "").replace(",", "").strip()
                        a = float(a_str) if a_str and a_str.replace(".", "").replace("-", "").replace(" ", "").isdigit() else 0
                        f = float(f_str) if f_str and f_str.replace(".", "").replace("-", "").replace(" ", "").isdigit() else 0
                        diff_val = round(a - f, 1)
                        is_better = a > f if a != 0 and f != 0 else False
                    except:
                        pass

                    bias = "Bullish" if is_better else "Bearish"
                    gold_bias = "Bearish" if bias == "Bullish" else "Bullish"

                    reaction_block = f"""
🌍 **Marktreaktion erwartet:**

📈 NAS100 {'↑' if is_better else '↓'}
📈 US30 {'↑' if is_better else '↓'}
🛢️ USOIL {'↑' if is_better else '↓'}
₿ BTC {'↑' if is_better else '↓'}
🟡 XAUUSD {'↓' if is_better else '↑'}
"""

                    analysis_text = f"""📊 **{country} | {title}**

🕒 **Status:** LIVE  •  **{event_time_berlin.strftime('%H:%M Uhr')}**

📈 Actual:   **{event['actual']}**
📊 Forecast: **{event['forecast']}**
📉 Previous: **{event['previous']}**

━━━━━━━━━━━━━━━━━━━
🧠 **Analyse:**
Die Daten liegen **{'über' if is_better else 'unter'}** den Erwartungen ({'+' if is_better else ''}{diff_val}).

━━━━━━━━━━━━━━━━━━━
{reaction_block.strip()}

━━━━━━━━━━━━━━━━━━━
💡 **Trading Bias:**
➡️ Indizes: **{bias}**
➡️ Gold: **{gold_bias}**
➡️ BTC: **{bias}**
"""

                    embed = discord.Embed(
                        title=f"📊 {country} — {title}",
                        description="**High Impact Event läuft JETZT!**",
                        color=color,
                        timestamp=now_berlin
                    )
                    embed.add_field(name="📊 Marktanalyse", value=analysis_text, inline=False)
                    embed.add_field(name="💱 Betroffene Märkte", value=get_pairs(country, title), inline=False)

                    msg = await channel.send(content=mention, embed=embed)
                    sent_events.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                    print(f"🚀 LIVE gesendet: {title} um {event_time_berlin.strftime('%H:%M')} MEZ", flush=True)

        except Exception as e:
            print(f
