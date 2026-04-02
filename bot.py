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

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

sent_events = set()
pre_alerts_1h = set()
pre_alerts_30m = set()
last_events = []
last_fetch_time = None
loop_started = False
message_ids_to_delete = {}

berlin_tz = tz.gettz("Europe/Berlin")


def get_mention():
    return "@everyone"


def get_pairs(country: str, title: str = "") -> str:
    c = country.upper()
    if "USD" in c or "US" in c:
        return "EURUSD, GBPUSD, USDJPY, NAS100, US30, XAUUSD"
    elif "EUR" in c:
        return "EURUSD, GBPUSD, USDJPY, DAX, XAUUSD"
    elif "JPY" in c:
        return "USDJPY, EURJPY, GBPJPY, Nikkei, XAUUSD"
    elif "CHF" in c:
        return "EURCHF, USDCHF, GBPCHF, XAUUSD"
    elif "CAD" in c:
        return "USDCAD, EURCAD, CADJPY, USOIL"
    elif "AUD" in c:
        return "AUDUSD, NZDUSD, AUDJPY, ASX"
    elif "NZD" in c:
        return "NZDUSD, AUDNZD, NZDJPY"
    elif "GBP" in c:
        return "GBPUSD, EURGBP, GBPJPY, FTSE"
    else:
        return "EURUSD, XAUUSD"


def get_color_and_impact_name(impact: str):
    if impact == "high":
        return 0xff0000, "🚨 HIGH IMPACT"
    else:
        return None, None


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
    elif "CHF" in country:
        return f"""{emoji} EURCHF {arrow if not is_better else '↓'}    {emoji} USDCHF {'↑' if is_better else '↓'}
🟡 XAUUSD {'↓' if is_better else '↑'}"""
    elif "CAD" in country:
        return f"""{emoji} USOIL {arrow}    {emoji} USDCAD {'↑' if is_better else '↓'}"""
    elif "AUD" in country:
        return f"""{emoji} ASX {arrow}    {emoji} AUDUSD {'↑' if is_better else '↓'}"""
    else:
        return f"""{emoji} Indizes {arrow}    🟡 Gold {'↓' if is_better else '↑'}"""


def get_events():
    global last_events, last_fetch_time

    if last_fetch_time and (datetime.now(timezone.utc) - last_fetch_time).total_seconds() < 120:
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

            actual = event.findtext("actual", "").strip()
            forecast = event.findtext("forecast", "").strip()
            previous = event.findtext("previous", "").strip()

            if impact_raw not in ["high", "3"]:
                continue

            if not title or time_str in ("", "All Day", "Tentative"):
                continue

            events.append({
                "title": title,
                "country": country,
                "date": date,
                "time": time_str,
                "impact": "high",
                "actual": actual,
                "forecast": forecast,
                "previous": previous
            })

        print(f"✅ {len(events)} HIGH IMPACT Events geladen", flush=True)
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

    print(f"🟢 News-Loop gestartet | Nur HIGH IMPACT", flush=True)

    while not client.is_closed():
        try:
            await delete_old_messages(channel)

            now_berlin = datetime.now(berlin_tz)
            tz_name = "MESZ" if now_berlin.utcoffset().total_seconds() == 7200 else "MEZ"

            events = get_events()

            for event in events:
                title = event["title"]
                country = event["country"]
                date_str = event["date"]
                time_str = event["time"]

                key = f"{title}_{date_str}_{time_str}"

                try:
                    naive_time = parser.parse(f"{date_str} {time_str}")
                    event_time_ny = naive_time.replace(tzinfo=tz.gettz("America/New_York"))
                    event_time_berlin = event_time_ny.astimezone(berlin_tz)
                except:
                    continue

                diff = (event_time_berlin - now_berlin).total_seconds()

                mention = get_mention()
                color, impact_name = get_color_and_impact_name("high")
                if color is None:
                    continue

                # 1 Stunde vorher
                if 3300 < diff < 3900 and key not in pre_alerts_1h:
                    minutes = int(diff / 60)
                    embed = discord.Embed(
                        title=f"{impact_name} – {country} {title}",
                        description=f"🕒 Event in ca. **{minutes} Minuten**",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_1h.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # 30 Minuten vorher
                if 1500 < diff < 2100 and key not in pre_alerts_30m:
                    minutes = int(diff / 60)
                    embed = discord.Embed(
                        title=f"{impact_name} – {country} {title}",
                        description=f"🕒 Event in ca. **{minutes} Minuten**",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_30m.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # LIVE EVENT mit kurzer Wartezeit auf Actual
                if -1200 < diff < 2400 and key not in sent_events:
                    actual_str = ""
                    for wait in range(4):   # max. 20 Sekunden warten
                        events = get_events()
                        for e in events:
                            if f"{e['title']}_{e['date']}_{e['time']}" == key:
                                actual_str = str(e.get("actual", "")).strip()
                                break
                        if actual_str and actual_str not in ["N/A", ""]:
                            break
                        await asyncio.sleep(5)

                    forecast_str = str(event.get("forecast", "")).strip()
                    previous_str = str(event.get("previous", "")).strip()

                    is_better = False
                    diff_val = "N/A"

                    try:
                        a_clean = actual_str.replace("K","000").replace("%","").replace(",","").replace(" ","").strip()
                        f_clean = forecast_str.replace("K","000").replace("%","").replace(",","").replace(" ","").strip()
                        if a_clean and a_clean not in ["N/A", "-", ""]:
                            a = float(a_clean)
                            if f_clean and f_clean not in ["N/A", "-", ""]:
                                f = float(f_clean)
                                diff_val = round(a - f, 1)
                                is_better = a > f
                    except:
                        pass

                    arrow = "↑" if is_better else "↓"
                    market_emoji = "📈" if is_better else "📉"

                    status_text = "✅ Die Daten sind **deutlich besser** als erwartet!" if is_better else "❌ Die Daten sind **schwächer** als erwartet!"

                    explanation = (
                        "Die veröffentlichten Zahlen sind **besser** als die Analysten erwartet haben. "
                        "Das zeigt, dass die Wirtschaft in diesem Bereich stärker ist als gedacht."
                        if is_better else
                        "Die veröffentlichten Zahlen sind **schwächer** als die Analysten erwartet haben. "
                        "Das zeigt, dass die Wirtschaft in diesem Bereich etwas langsamer läuft als gedacht."
                    )

                    actual_display = actual_str if actual_str and actual_str not in ["N/A", ""] else "Noch keine Daten"

                    analysis_text = f"""🕒 **Status:** LIVE  •  **{event_time_berlin.strftime('%H:%M')} MESZ**

{status_text}

🧠 Einfache Erklärung:
{explanation}

{market_emoji} Was das für den Markt bedeutet:
{get_market_reaction(event["country"], is_better)}

💡 Praktischer Tipp für Anfänger:
Warte am besten **10–15 Minuten**, bis sich der erste starke Ausschlag beruhigt hat. Die ersten Minuten sind extrem volatil!

━━━━━━━━━━━━━━━━━━━
📊 Technische Daten:
Actual:     **{actual_display}** {arrow if is_better else ''}
Forecast:   **{forecast_str if forecast_str else "N/A"}**
Previous:   **{previous_str if previous_str else "N/A"}**
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

        await asyncio.sleep(120)  # ruhiger Rhythmus, um Rate-Limit zu vermeiden


@client.event
async def on_ready():
    global loop_started
    print(f"🤖 Eingeloggt als {client.user} | Nur HIGH IMPACT aktiv", flush=True)
    if not loop_started:
        client.loop.create_task(news_loop())
        loop_started = True


if __name__ == "__main__":
    if not TOKEN or CHANNEL_ID == 0:
        print("❌ TOKEN oder CHANNEL_ID fehlt!", flush=True)
        sys.exit(1)
    client.run(TOKEN)
