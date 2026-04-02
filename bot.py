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
        return "EURUSD • GBPUSD • USDJPY\nNAS100 • US30 • XAUUSD • USOIL • BTC"
    elif "EUR" in c:
        return "EURUSD • GBPUSD • USDJPY\nDAX • XAUUSD"
    elif "JPY" in c:
        return "USDJPY • EURJPY • GBPJPY\nNikkei • XAUUSD"
    elif "CHF" in c:
        return "EURCHF • USDCHF • GBPCHF • XAUUSD"
    elif "CAD" in c:
        return "USDCAD • EURCAD • CADJPY • USOIL"
    elif "AUD" in c:
        return "AUDUSD • NZDUSD • AUDJPY • ASX"
    else:
        return "EURUSD • XAUUSD"


def get_color_and_impact_name(impact: str):
    if impact == "high":
        return 0xff0000, "🚨 HIGH IMPACT"
    else:
        return None, None   # Nur High Impact


def get_market_reaction(country: str, is_better: bool):
    arrow = "↑" if is_better else "↓"
    if "USD" in country or "US" in country:
        return f"📈 US-Indizes (NAS100, US30) → {arrow}\n📈 USD → wird stärker\n📈 USOIL & BTC → können profitieren\n📉 XAUUSD (Gold) → {'fällt' if is_better else 'steigt'} häufig"
    elif "EUR" in country:
        return f"📈 DAX → {arrow}\n📈 EURUSD → {'↑' if is_better else '↓'}\n📉 XAUUSD → {'↓' if is_better else '↑'}"
    elif "JPY" in country:
        return f"📈 Nikkei → {arrow}\n📈 USDJPY → {'↓' if is_better else '↑'}\n📉 XAUUSD → {'↓' if is_better else '↑'}"
    elif "CHF" in country:
        return f"📈 EURCHF → {'↓' if is_better else '↑'}\n📈 USDCHF → {arrow}\n📉 XAUUSD → {'↓' if is_better else '↑'}"
    else:
        return f"Indizes → {arrow}\nXAUUSD → {'↓' if is_better else '↑'}"


def get_events():
    global last_events, last_fetch_time

    if last_fetch_time and (datetime.now(timezone.utc) - last_fetch_time).total_seconds() < 60:
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
                continue   # Nur HIGH IMPACT

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


async def news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Channel nicht gefunden!", flush=True)
        return

    print(f"🟢 News-Loop gestartet | Nur HIGH IMPACT", flush=True)

    while not client.is_closed():
        try:
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
                except Exception:
                    continue

                diff = (event_time_berlin - now_berlin).total_seconds()

                mention = get_mention()
                color, impact_name = get_color_and_impact_name("high")
                if color is None:
                    continue

                # ==================== 1 STUNDE VORHER ====================
                if 3300 < diff < 3900 and key not in pre_alerts_1h:
                    print(f"✅ 1h-VORWARNUNG: {title}", flush=True)
                    pre_text = f"""⏰ 1 Stunde vorher

@everyone

🚨 HIGH IMPACT – {country} {title}

🕒 Event in ca. 1 Stunde ({event_time_berlin.strftime('%H:%M')} {tz_name})

⸻

📊 Event Überblick:
Die {title} zeigen, wie stark die Wirtschaft in {country} aktuell läuft.

👉 Einer der wichtigsten kurzfristigen Indikatoren für die {country}-Wirtschaft

⸻

🧠 Was du erwarten kannst:
	•	Hohe Volatilität rund um die Veröffentlichung
	•	Schnelle Bewegungen in USD-Paaren & Indizes
	•	Oft starke erste Reaktion + möglicher Richtungswechsel

⸻

💱 Wichtige Märkte im Fokus:
{get_pairs(country, title)}

⸻

💡 Vorbereitung:
✔️ Wichtige Levels markieren
✔️ Kein impulsives Trading direkt beim Release
✔️ Plan vor dem Event festlegen
"""

                    embed = discord.Embed(
                        title=f"🚨 HIGH IMPACT – {country} {title}",
                        description="",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    embed.add_field(name="", value=pre_text, inline=False)

                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_1h.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # ==================== 30 MINUTEN VORHER ====================
                if 1500 < diff < 2100 and key not in pre_alerts_30m:
                    print(f"✅ 30m-VORWARNUNG: {title}", flush=True)
                    pre_text = f"""⏰ 30 Minuten vorher

@everyone

🚨 HIGH IMPACT – {country} {title}

🕒 Event in ca. 30 Minuten ({event_time_berlin.strftime('%H:%M')} {tz_name})

⸻

📊 Event Überblick:
Die {title} zeigen, wie stark die Wirtschaft in {country} aktuell läuft.

👉 Hohe Volatilität erwartet

⸻

💱 Wichtige Märkte im Fokus:
{get_pairs(country, title)}

⸻

💡 Tipp:
Bleib ruhig und halte deinen Plan ein.
"""

                    embed = discord.Embed(
                        title=f"🚨 HIGH IMPACT – {country} {title}",
                        description="",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    embed.add_field(name="", value=pre_text, inline=False)

                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_30m.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # ==================== LIVE EVENT ====================
                if -900 < diff < 1800 and key not in sent_events:
                    print(f"🚀 Versuche LIVE für: {title}", flush=True)

                    actual_str = ""
                    for wait in range(8):   # max ~40 Sekunden warten auf Actual
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
                    status_text = "✅ Die Daten sind besser als erwartet!" if is_better else "❌ Die Daten sind schwächer als erwartet!"

                    actual_display = actual_str if actual_str and actual_str not in ["N/A", ""] else "Noch keine Daten"

                    analysis_text = f"""📅 Event läuft JETZT!

📊 Marktanalyse
⏱️ Status: LIVE

⸻

{status_text}

🧠 Einfache Erklärung:
Die {title} zeigen, wie stark die Wirtschaft in {country} aktuell läuft.

👉 Die Zahl ist {'niedriger' if is_better else 'höher'} als erwartet
➡️ {'Weniger' if is_better else 'Mehr'} Arbeitslose / Inflation / etc. = {'stärkerer' if is_better else 'schwächerer'} Markt
➡️ Das ist ein {'positives' if is_better else 'negatives'} Signal für die Wirtschaft

⸻

📈 Was das für den Markt bedeutet:
{get_market_reaction(country, is_better)}

⸻

💡 Warum reagiert der Markt so?
Starke/schwache Daten verändern die Erwartungen an die Notenbank und die Wirtschaftslage.
Investoren passen ihre Risikobereitschaft an.

⸻

⚠️ Praktischer Tipp für Anfänger:
Die ersten Minuten nach solchen News sind extrem volatil und unberechenbar

👉 Warte 10–15 Minuten, bis sich eine klare Richtung bildet
👉 Vermeide impulsive Einstiege direkt nach Release

⸻

━━━━━━━━━━━━━━━━━━━
📊 Technische Daten:
• Actual:     {actual_display}
• Forecast:   {forecast_str if forecast_str else "N/A"}
• Previous:   {previous_str if previous_str else "N/A"}
• Abweichung: {'+' if is_better else ''}{diff_val} ({'positiv' if is_better else 'negativ'})

⸻

💱 Betroffene Märkte:
{get_pairs(country, title)}

⸻

💡 Fazit:
{'Stärker' if is_better else 'Schwächer'} als erwartete Daten = {'positive' if is_better else 'vorsichtige'} Marktstimmung + Bewegung in mehreren Assets
"""

                    embed = discord.Embed(
                        title=f"🚨 HIGH IMPACT – {country} {title}",
                        description="",
                        color=0xff0000,
                        timestamp=now_berlin
                    )
                    embed.add_field(name="", value=analysis_text, inline=False)

                    msg = await channel.send(content=mention, embed=embed)
                    sent_events.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                    print(f"🚀 LIVE gesendet: {title} | Actual: {actual_display}", flush=True)

        except Exception as e:
            print(f"❌ Loop-Fehler: {e}", flush=True)

        await asyncio.sleep(30)   # alle 30 Sekunden prüfen → sehr gute Reaktionszeit


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
