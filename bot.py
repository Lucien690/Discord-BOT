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

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# ==================== VARIABLEN ====================
sent_events = set()
pre_alerts_2h = set()
last_events = []
last_fetch_time = None
loop_started = False
message_ids_to_delete = {}

berlin_tz = tz.gettz("Europe/Berlin")


def get_mention():
    return "@everyone"


def get_pairs(country: str, title: str = "") -> str:
    return "NAS100, US30, XAUUSD, USOIL, BTC"


def get_color_and_impact_name(impact: str):
    if impact == "high":
        return 0xff0000, "🚨 HIGH IMPACT"
    else:
        return 0xffaa00, "⚠️ MEDIUM IMPACT"


def get_market_reaction(country: str, is_better: bool):
    arrow = "↑" if is_better else "↓"
    emoji = "📈" if is_better else "📉"

    if "USD" in country or "US" in country:
        return f"""{emoji} NAS100 {arrow}    {emoji} US30 {arrow}
🛢️ USOIL {arrow}     ₿ BTC {arrow}
🟡 XAUUSD {'↓' if is_better else '↑'}"""
    elif "EUR" in country:
        return f"""{emoji} DAX {arrow}    {emoji} EURUSD {'↑' if is_better else '↓'}
🟡 XAUUSD {'↓' if is_better else '↑'}"""
    elif "JPY" in country:
        return f"""{emoji} Nikkei {arrow}    {emoji} USDJPY {'↓' if is_better else '↑'}
🟡 XAUUSD {'↓' if is_better else '↑'}"""
    elif "CAD" in country:
        return f"""{emoji} USOIL {arrow}    {emoji} CAD {'↑' if is_better else '↓'}"""
    elif "AUD" in country:
        return f"""{emoji} ASX {arrow}    {emoji} AUDUSD {'↑' if is_better else '↓'}"""
    else:
        return f"""{emoji} Indizes {arrow}    🟡 Gold {'↓' if is_better else '↑'}"""


def get_events():
    global last_events, last_fetch_time

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

        print(f"✅ {len(events)} Events (High + Medium Impact) geladen", flush=True)
        last_events = events
        last_fetch_time = datetime.now(timezone.utc)
        return events

    except Exception as e:
        print(f"❌ Fehler beim Laden: {e}", flush=True)
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

    print(f"🟢 News-Loop gestartet | 2-Stunden-Vorwarnung + Live", flush=True)

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

                print(f"🔍 Prüfe Event: {title} | diff = {diff:.0f} Sekunden", flush=True)

                mention = get_mention()
                color, impact_name = get_color_and_impact_name(impact)

                # ==================== 2-STUNDEN-VORWARNUNG (jetzt breiter) ====================
                if 3600 < diff < 10800 and key not in pre_alerts_2h:   # 60 – 180 Minuten vorher (robuster)
                    minutes = int(diff / 60)
                    print(f"🔔 2H-Vorwarnung gesendet: {title} (in {minutes} Minuten)", flush=True)
                    embed = discord.Embed(
                        title=f"{impact_name} – {country} {title}",
                        description=f"🕒 Event in ca. **{minutes} Minuten** (um {event_time_berlin.strftime('%H:%M')} MEZ)",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    embed.add_field(name="🌍 Volatilität", value="Hohe Marktreaktion erwartet", inline=False)
                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_2h.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # ==================== LIVE EVENT ====================
                if -300 < diff < 900 and key not in sent_events:
                    print(f"🚀 LIVE Event gesendet: {title}", flush=True)

                    is_better = False
                    diff_val = 0
                    try:
                        a = float(str(event["actual"]).replace("K","000").replace("%","").replace(",","").strip() or 0)
                        f = float(str(event["forecast"]).replace("K","000").replace("%","").replace(",","").strip() or 0)
                        diff_val = round(a - f, 1)
                        is_better = a > f if a and f else False
                    except:
                        pass

                    arrow = "↑" if is_better else "↓"
                    market_emoji = "📈" if is_better else "📉"

                    analysis_text = f"""🕒 **Status:** LIVE  •  **{event_time_berlin.strftime('%H:%M MEZ')}**

{'✅' if is_better else '❌'} Die Daten sind **{'deutlich besser' if is_better else 'schwächer'}** als erwartet!

🧠 Einfache Erklärung:
Die Zahlen liegen **{'über' if is_better else 'unter'}** den Erwartungen. Das ist ein {'positives' if is_better else 'negatives'} Signal.

{market_emoji} Was das für den Markt bedeutet:
{get_market_reaction(event["country"], is_better)}

💡 Praktischer Tipp für Anfänger:
Warte am besten **10–15 Minuten**, bis sich der erste starke Ausschlag beruhigt hat. Die ersten Minuten sind extrem volatil!

━━━━━━━━━━━━━━━━━━━
📊 Technische Daten:
Actual:     **{event['actual']}** {arrow}
Forecast:   **{event['forecast']}**
Previous:   **{event['previous']}**
Abweichung: **{'+' if is_better else ''}{diff_val}** ({'besser' if is_better else 'schlechter'} als erwartet)
"""

                    embed = discord.Embed(
                        title=f"{impact_name} – {country} {title}",
                        description="**Event läuft JETZT!**",
                        color=color,
                        timestamp=now_berlin
                    )
                    embed.add_field(name="📊 Marktanalyse", value=analysis_text, inline=False)
                    embed.add_field(name="💱 Betroffene Märkte", value=get_pairs(country, title), inline=False)

                    msg = await channel.send(content=mention, embed=embed)
                    sent_events.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

        except Exception as e:
            print(f"❌ Loop-Fehler: {e}", flush=True)

        await asyncio.sleep(60)


# ==================== FAKE NEWS TEST ====================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content_lower = message.content.lower()
    if client.user.mentioned_in(message) and ("fake" in content_lower or "test" in content_lower):
        print("🧪 Fake News Test ausgelöst!", flush=True)

        analysis_text = """🕒 **Status:** LIVE  •  **14:30 MEZ** (Test)

✅ Die Daten sind **deutlich besser** als erwartet!

🧠 Einfache Erklärung:
Die Zahlen liegen **über** den Erwartungen. Das ist ein positives Signal für die US-Wirtschaft.

📈 Was das für den Markt bedeutet:
📈 NAS100 ↑    📈 US30 ↑
🛢️ USOIL ↑     ₿ BTC ↑
🟡 XAUUSD ↓   (Gold fällt meist)

💡 Praktischer Tipp für Anfänger:
Warte am besten **10–15 Minuten**, bis sich der erste starke Ausschlag beruhigt hat. Die ersten Minuten sind extrem volatil!

━━━━━━━━━━━━━━━━━━━
📊 Technische Daten:
Actual:     **250K** ↑
Forecast:   **180K**
Previous:   **170K**
Abweichung: **+70K** (besser als erwartet)
"""

        embed = discord.Embed(
            title="🚨 HIGH IMPACT – USD Fake Event (Test)",
            description="**TEST – nur zur Überprüfung**",
            color=0xff0000,
            timestamp=datetime.now(berlin_tz)
        )
        embed.add_field(name="📊 Marktanalyse", value=analysis_text, inline=False)
        embed.add_field(name="💱 Betroffene Märkte", value=get_pairs("USD"), inline=False)

        await message.channel.send(content=get_mention(), embed=embed)


@client.event
async def on_ready():
    global loop_started
    print(f"🤖 Eingeloggt als {client.user}", flush=True)
    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True


if __name__ == "__main__":
    if not TOKEN or CHANNEL_ID == 0:
        print("❌ TOKEN oder CHANNEL_ID fehlt!", flush=True)
        sys.exit(1)
    client.run(TOKEN)
