import discord
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import os
import sys
from dateutil import parser, tz

sys.stdout.reconfigure(line_buffering=True)

print("🚀 SCRIPT STARTET", flush=True)

# ==================== KONFIGURATION ====================
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

# Rollen-IDs (unbedingt in .env eintragen!)
HIGH_ROLE_ID = int(os.getenv("HIGH_ROLE_ID", "0"))
MEDIUM_ROLE_ID = int(os.getenv("MEDIUM_ROLE_ID", "0"))
LOW_ROLE_ID = int(os.getenv("LOW_ROLE_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# ==================== VARIABLEN ====================
sent_events = set()
pre_alerts_1h = set()
pre_alerts_30m = set()
last_events = []
last_fetch_time = None
loop_started = False
message_ids_to_delete = {}   # {message_id: delete_time}

berlin_tz = tz.gettz("Europe/Berlin")


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
    global last_events, last_fetch_time

    # Cache: Nur alle 4 Minuten neu laden
    if last_fetch_time and (datetime.now(timezone.utc) - last_fetch_time).total_seconds() < 240:
        return last_events

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
            impact_raw = event.findtext("impact", "low").lower().strip()

            actual = event.findtext("actual", "N/A")
            forecast = event.findtext("forecast", "N/A")
            previous = event.findtext("previous", "N/A")

            if impact_raw in ["high", "3", "high impact"]:
                impact = "high"
            elif impact_raw in ["medium", "2", "med"]:
                impact = "medium"
            elif impact_raw in ["low", "1"]:
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

        print(f"✅ {len(events)} Events erfolgreich geladen", flush=True)
        last_events = events
        last_fetch_time = datetime.now(timezone.utc)
        return events

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            print("⚠️ Rate Limit (429) erreicht – warte länger...", flush=True)
        else:
            print(f"❌ HTTP Fehler: {e}", flush=True)
    except Exception as e:
        print(f"❌ Fehler beim Laden der Events: {e}", flush=True)

    return last_events


async def delete_old_messages(channel):
    now = datetime.now(timezone.utc)
    to_delete = [msg_id for msg_id, del_time in list(message_ids_to_delete.items()) if now > del_time]
    for msg_id in to_delete:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.delete()
            print(f"🗑️ Nachricht {msg_id} nach 24h gelöscht", flush=True)
        except:
            pass
        message_ids_to_delete.pop(msg_id, None)


async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Channel nicht gefunden!", flush=True)
        return

    print(f"🟢 News-Loop gestartet | Deutsche Zeit (MEZ/MESZ)", flush=True)

    while not client.is_closed():
        try:
            await delete_old_messages(channel)

            now_berlin = datetime.now(berlin_tz)
            print(f"⏰ Check um {now_berlin.strftime('%Y-%m-%d %H:%M:%S')} (MEZ/MESZ)", flush=True)

            events = get_events()

            for event in events:
                title = event["title"]
                country = event["country"]
                date_str = event["date"]
                time_str = event["time"]
                impact = event["impact"]

                key = f"{title}_{date_str}_{time_str}"

                try:
                    naive_time = parser.parse(f"{date_str} {time_str}")
                    event_time_ny = naive_time.replace(tzinfo=tz.gettz("America/New_York"))
                    event_time_berlin = event_time_ny.astimezone(berlin_tz)
                except Exception:
                    continue

                diff = (event_time_berlin - now_berlin).total_seconds()

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

                # LIVE Event
                if 0 < diff < 180 and key not in sent_events:
                    is_better = False
                    diff_val = 0
                    try:
                        a_str = str(event["actual"]).replace("K", "000").replace("%", "").replace(",", "").strip()
                        f_str = str(event["forecast"]).replace("K", "000").replace("%", "").replace(",", "").strip()
                        a = float(a_str) if a_str and a_str.replace(".", "").replace("-", "").replace(" ", "").isdigit() else 0.0
                        f = float(f_str) if f_str and f_str.replace(".", "").replace("-", "").replace(" ", "").isdigit() else 0.0
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

                    print(f"🚀 LIVE gesendet: {title}", flush=True)

        except Exception as e:
            print(f"❌ Loop-Fehler: {e}", flush=True)

        await asyncio.sleep(300)  # 5 Minuten – Rate-Limit-sicher


# ==================== FAKE NEWS TEST COMMAND ====================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content_lower = message.content.lower()

    # Debug in Logs
    print(f"📨 Nachricht erhalten: {message.content}", flush=True)
    print(f"🤖 Bot erwähnt? {client.user.mentioned_in(message)}", flush=True)

    # Trigger: Bot erwähnen + "fake" oder "test" im Text
    if client.user.mentioned_in(message) and ("fake" in content_lower or "test" in content_lower):
        print("🧪 Fake News Test ausgelöst!", flush=True)

        analysis_text = """📊 **USD | Fake High Impact Event**

🕒 **Status:** LIVE

📈 Actual:   **250K**
📊 Forecast: **180K**
📉 Previous: **170K**

━━━━━━━━━━━━━━━━━━━
🧠 **Analyse:**
Die Daten liegen **deutlich über** den Erwartungen (+70K).

━━━━━━━━━━━━━━━━━━━
🌍 **Marktreaktion erwartet:**

📈 NAS100 ↑
📈 US30 ↑
🛢️ USOIL ↑
₿ BTC ↑
🟡 XAUUSD ↓

━━━━━━━━━━━━━━━━━━━
💡 **Trading Bias:**
➡️ Indizes: **Bullish**
➡️ Gold: **Bearish**
➡️ BTC: **Bullish**
"""

        embed = discord.Embed(
            title="📊 USD — Fake Event (Test)",
            description="**TEST — nur zur Überprüfung**",
            color=0xff0000
        )
        embed.add_field(name="📊 Marktanalyse", value=analysis_text, inline=False)
        embed.add_field(name="💱 Betroffene Märkte", value=get_pairs("USD"), inline=False)

        await message.channel.send(content="<@&HIGH_ROLE_ID> TEST", embed=embed)
        return


@client.event
async def on_ready():
    global loop_started
    print(f"🤖 Eingeloggt als {client.user}", flush=True)
    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True


if __name__ == "__main__":
    if not TOKEN or CHANNEL_ID == 0:
        print("❌ TOKEN oder CHANNEL_ID fehlt in .env!", flush=True)
        sys.exit(1)
    client.run(TOKEN)
