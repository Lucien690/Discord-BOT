import discord
import asyncio
import requests
from datetime import datetime, timedelta, timezone
import os
import sys
from dateutil import parser, tz

sys.stdout.reconfigure(line_buffering=True)

print("🚀 SCRIPT STARTET – JBlanked News API Version (kostenlos)", flush=True)

# ==================== KONFIGURATION ====================
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
JBLANKED_API_KEY = os.getenv("JBLANKED_API_KEY")   # ← Hier wird dein Key geladen

if not JBLANKED_API_KEY:
    print("❌ WARNUNG: JBLANKED_API_KEY fehlt in den Environment Variables!", flush=True)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# ==================== VARIABLEN ====================
sent_events = set()
pre_alerts_1h = set()
last_events = []
last_fetch_time = None
loop_started = False
message_ids_to_delete = {}
live_messages = {}

berlin_tz = tz.gettz("Europe/Berlin")
utc_tz = tz.gettz("UTC")


def get_mention():
    return "@everyone"


def get_pairs(country: str, title: str = "") -> str:
    if "USD" in country or "US" in country:
        return "NAS100, US30, XAUUSD, USOIL, BTC"
    elif "EUR" in country:
        return "DAX, EURUSD, XAUUSD"
    elif "JPY" in country:
        return "Nikkei, USDJPY, XAUUSD"
    elif "CAD" in country:
        return "USOIL, CAD"
    elif "AUD" in country:
        return "ASX, AUDUSD"
    else:
        return "Indizes, XAUUSD"


def get_color_and_impact_name(impact: str):
    if impact.lower() in ["high", "3"]:
        return 0xff0000, "🚨 HIGH IMPACT"
    else:
        return 0x00ff00, "📅 LOW IMPACT"


def get_market_reaction(country: str, has_actual: bool = False):
    if not has_actual:
        return "• Marktreaktion hängt von den veröffentlichten Daten ab\n• Hohe Volatilität erwartet"
    
    if "USD" in country or "US" in country:
        return "• 📈 NAS100 → steigt\n• 📈 US30 → steigt\n• 🛢️ USOIL → steigt\n• ₿ BTC → steigt\n• 🟡 Gold (XAUUSD) → fällt"
    elif "EUR" in country:
        return "• 📉 DAX → fällt\n• 📉 EURUSD → fällt\n• 🟡 Gold (XAUUSD) → steigt"
    else:
        return "• Marktreaktion je nach Daten möglich"


def get_events():
    global last_events, last_fetch_time

    if last_fetch_time and (datetime.now(timezone.utc) - last_fetch_time).total_seconds() < 600:
        return last_events

    url = "https://www.jblanked.com/news/api/forex-factory/calendar/today/"

    headers = {
        "Authorization": f"Bearer {JBLANKED_API_KEY}"   # Key wird hier verwendet
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        events = []
        for ev in data:
            try:
                title = ev.get("Event", ev.get("Name", "N/A"))
                country = ev.get("Currency", "N/A")
                date_time_str = ev.get("Date", "") or ev.get("Time", "")
                impact = str(ev.get("Impact", "low")).lower()
                actual = ev.get("Actual", "N/A")
                forecast = ev.get("Forecast", "N/A")
                previous = ev.get("Previous", "N/A")

                if not title or not date_time_str:
                    continue

                if " " in date_time_str:
                    date_str, time_str = date_time_str.split(" ", 1)
                else:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    time_str = date_time_str[:5] if len(date_time_str) >= 5 else date_time_str

                events.append({
                    "title": title,
                    "country": country,
                    "date": date_str,
                    "time": time_str,
                    "impact": "high" if impact in ["high", "3"] else "low",
                    "actual": actual,
                    "forecast": forecast,
                    "previous": previous
                })
            except:
                continue

        print(f"✅ {len(events)} Events von JBlanked geladen", flush=True)
        last_events = events
        last_fetch_time = datetime.now(timezone.utc)
        return events

    except Exception as e:
        print(f"❌ Fehler beim Laden von JBlanked API: {e}", flush=True)
        return last_events


# ==================== Der Rest bleibt unverändert ====================
# (delete_old_messages, news_loop, on_message, on_ready usw.)

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

    print(f"🟢 News-Loop gestartet | High + Low Impact (JBlanked API)", flush=True)

    while not client.is_closed():
        try:
            await delete_old_messages(channel)

            now_berlin = datetime.now(berlin_tz)
            print(f"⏰ Check um {now_berlin.strftime('%H:%M:%S %d.%m.%Y')} MEZ/MESZ", flush=True)

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
                    event_time_utc = naive_time.replace(tzinfo=utc_tz)
                    event_time_berlin = event_time_utc.astimezone(berlin_tz)
                    print(f"🕒 Event: {title} → Berlin: {event_time_berlin.strftime('%d.%m.%Y %H:%M')}", flush=True)
                except Exception:
                    continue

                diff_seconds = (event_time_berlin - now_berlin).total_seconds()

                mention = get_mention()
                color, impact_name = get_color_and_impact_name(impact)

                if 3000 < diff_seconds < 4200 and key not in pre_alerts_1h:
                    minutes = int(diff_seconds / 60)
                    embed = discord.Embed(
                        title=f"{impact_name} – {country} {title}",
                        description=f"🕒 **Erinnerung:** Event in ca. **{minutes} Minuten**",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    embed.add_field(name="🌍 Volatilität", value="Marktreaktion erwartet", inline=False)
                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_1h.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                if -60 < diff_seconds < 600 and key not in sent_events:
                    print(f"🚀 LIVE Event gesendet: {title}", flush=True)

                    actual = event.get("actual", "N/A")
                    forecast = event.get("forecast", "N/A")
                    previous = event.get("previous", "N/A")

                    has_actual = actual not in ["N/A", "", "—", "Wird gerade veröffentlicht..."]

                    actual_line = f"Aktuell (Actual): {actual} 📈" if has_actual else "Aktuell (Actual): Wird gerade veröffentlicht..."

                    analysis_text = f"""🕒 Status: LIVE • {event_time_berlin.strftime('%H:%M MEZ/MESZ')}
━━━━━━━━━━━━━━━━━━━
📊 Wirtschaftsdaten-Update

{actual_line}
Erwartung (Forecast): {forecast}
Vorher (Previous): {previous}
━━━━━━━━━━━━━━━━━━━
🧠 Einfache Erklärung:

Die veröffentlichten Zahlen liegen deutlich über den Erwartungen.
Das zeigt, dass die Wirtschaft aktuell stärker läuft als gedacht.

➡️ Grundsätzlich positiv für den Markt
━━━━━━━━━━━━━━━━━━━
📈 Marktreaktion (typisch):
{get_market_reaction(country, has_actual)}
━━━━━━━━━━━━━━━━━━━
⚠️ Wichtiger Hinweis für Anfänger:

Die ersten Minuten nach solchen News sind sehr volatil.

💡 Tipp:
Warte 10–15 Minuten, bis sich der Markt beruhigt hat.
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
                    live_messages[key] = msg

                if key in live_messages:
                    msg = live_messages[key]
                    actual = event.get("actual", "N/A")
                    if actual not in ["N/A", "", "—", "Wird gerade veröffentlicht..."]:
                        new_analysis_text = f"""🕒 Status: LIVE • {event_time_berlin.strftime('%H:%M MEZ/MESZ')}
━━━━━━━━━━━━━━━━━━━
📊 Wirtschaftsdaten-Update

Aktuell (Actual): {actual} 📈
Erwartung (Forecast): {event.get('forecast', 'N/A')}
Vorher (Previous): {event.get('previous', 'N/A')}
━━━━━━━━━━━━━━━━━━━
🧠 Einfache Erklärung:

Die veröffentlichten Zahlen liegen deutlich über den Erwartungen.
Das zeigt, dass die Wirtschaft aktuell stärker läuft als gedacht.

➡️ Grundsätzlich positiv für den Markt
━━━━━━━━━━━━━━━━━━━
📈 Marktreaktion (typisch):
{get_market_reaction(country, True)}
━━━━━━━━━━━━━━━━━━━
⚠️ Wichtiger Hinweis für Anfänger:

Die ersten Minuten nach solchen News sind sehr volatil.

💡 Tipp:
Warte 10–15 Minuten, bis sich der Markt beruhigt hat.
"""

                        new_embed = discord.Embed(
                            title=f"{impact_name} – {country} {title}",
                            description="**Event läuft JETZT!** (aktualisiert)",
                            color=color,
                            timestamp=now_berlin
                        )
                        new_embed.add_field(name="📊 Marktanalyse", value=new_analysis_text, inline=False)
                        new_embed.add_field(name="💱 Betroffene Märkte", value=get_pairs(country, title), inline=False)

                        try:
                            await msg.edit(embed=new_embed)
                            print(f"✏️ Nachricht für {title} editiert", flush=True)
                            del live_messages[key]
                        except:
                            pass

        except Exception as e:
            print(f"❌ Loop-Fehler: {e}", flush=True)

        await asyncio.sleep(30)


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    content_lower = message.content.lower()
    if client.user.mentioned_in(message) and ("test" in content_lower or "fake" in content_lower):
        print("🧪 Test-Command ausgelöst!", flush=True)


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
