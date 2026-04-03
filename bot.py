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
last_events = []
last_fetch_time = None
loop_started = False
message_ids_to_delete = {}    # Für 24h-Löschung
live_messages = {}            # Für Editieren der LIVE-Nachricht

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
    if impact == "high":
        return 0xff0000, "🚨 HIGH IMPACT"
    elif impact == "medium":
        return 0xffaa00, "⚠️ MEDIUM IMPACT"
    else:
        return 0x00ff00, "📅 LOW IMPACT"


def get_market_reaction(country: str):
    if "USD" in country or "US" in country:
        return "• 📈 NAS100 → steigt\n• 📈 US30 → steigt\n• 🛢️ USOIL → steigt\n• ₿ BTC → steigt\n• 🟡 Gold (XAUUSD) → fällt"
    elif "EUR" in country:
        return "• 📉 DAX → fällt\n• 📉 EURUSD → fällt\n• 🟡 Gold (XAUUSD) → steigt"
    else:
        return "• Marktreaktion je nach Währung möglich"


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

            if impact_raw in ["high", "3"]:
                impact = "high"
            elif impact_raw in ["medium", "2"]:
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

        print(f"✅ {len(events)} Events geladen", flush=True)
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

    print(f"🟢 News-Loop gestartet | 1h Reminder + Edit-Funktion", flush=True)

    while not client.is_closed():
        try:
            await delete_old_messages(channel)

            now_berlin = datetime.now(berlin_tz)

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
                except Exception:
                    continue

                diff_seconds = (event_time_berlin - now_berlin).total_seconds()

                mention = get_mention()
                color, impact_name = get_color_and_impact_name(impact)

                # ==================== 1-STUNDEN-REMINDER ====================
                if 3000 < diff_seconds < 4200 and key not in pre_alerts_1h:
                    minutes = int(diff_seconds / 60)
                    embed = discord.Embed(
                        title=f"{impact_name} – {country} {title}",
                        description=f"🕒 **Erinnerung:** Event in ca. **{minutes} Minuten** (um {event_time_berlin.strftime('%H:%M')} MEZ/MESZ)",
                        color=color,
                        timestamp=event_time_berlin
                    )
                    embed.add_field(name="🌍 Volatilität", value="Marktreaktion erwartet", inline=False)
                    msg = await channel.send(content=mention, embed=embed)
                    pre_alerts_1h.add(key)
                    message_ids_to_delete[msg.id] = event_time_berlin + timedelta(hours=24)

                # ==================== LIVE-POST ====================
                if impact == "high" and -180 < diff_seconds < 900 and key not in sent_events:
                    print(f"🚀 LIVE High-Impact Event gesendet: {title}", flush=True)

                    actual = event.get("actual", "N/A")
                    forecast = event.get("forecast", "N/A")
                    previous = event.get("previous", "N/A")

                    actual_line = f"Aktuell (Actual): {actual} 📈" if actual not in ["N/A", ""] else "Aktuell (Actual): Wird gerade veröffentlicht..."

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
{get_market_reaction(country)}
━━━━━━━━━━━━━━━━━━━
⚠️ Wichtiger Hinweis für Anfänger:

Die ersten Minuten nach solchen News sind sehr volatil.

💡 Tipp:
Warte 10–15 Minuten, bis sich der Markt beruhigt hat, bevor du einen Trade eingehst.
━━━━━━━━━━━━━━━━━━━
📊 Kurze Analyse:
• Starke Abweichung zwischen Forecast und Actual
• Deutet auf positive Marktstimmung hin
• Kurzfristig: Momentum nach oben möglich
• Trotzdem: Vorsicht vor schnellen Gegenbewegungen
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
                    live_messages[key] = msg   # Für späteres Editieren

                # ==================== Actual prüfen und Nachricht editieren ====================
                if key in live_messages and impact == "high":
                    msg = live_messages[key]
                    actual = event.get("actual", "N/A")
                    if actual not in ["N/A", "", "Wird gerade veröffentlicht..."]:
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
{get_market_reaction(country)}
━━━━━━━━━━━━━━━━━━━
⚠️ Wichtiger Hinweis für Anfänger:

Die ersten Minuten nach solchen News sind sehr volatil.

💡 Tipp:
Warte 10–15 Minuten, bis sich der Markt beruhigt hat, bevor du einen Trade eingehst.
━━━━━━━━━━━━━━━━━━━
📊 Kurze Analyse:
• Starke Abweichung zwischen Forecast und Actual
• Deutet auf positive Marktstimmung hin
• Kurzfristig: Momentum nach oben möglich
• Trotzdem: Vorsicht vor schnellen Gegenbewegungen
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


# ==================== TEST-COMMAND ====================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content_lower = message.content.lower()
    if client.user.mentioned_in(message) and ("test" in content_lower or "fake" in content_lower):
        print("🧪 Test-Command ausgelöst!", flush=True)

        test_analysis = """🕒 Status: LIVE • 14:30 MEZ/MESZ
━━━━━━━━━━━━━━━━━━━
📊 Wirtschaftsdaten-Update

Aktuell (Actual): 250K 📈
Erwartung (Forecast): 180K
Vorher (Previous): 170K
━━━━━━━━━━━━━━━━━━━
🧠 Einfache Erklärung:

Die veröffentlichten Zahlen liegen deutlich über den Erwartungen.
Das zeigt, dass die Wirtschaft aktuell stärker läuft als gedacht.

➡️ Grundsätzlich positiv für den Markt
━━━━━━━━━━━━━━━━━━━
📈 Marktreaktion (typisch):
• 📈 NAS100 → steigt
• 📈 US30 → steigt
• 🛢️ USOIL → steigt
• ₿ BTC → steigt
• 🟡 Gold (XAUUSD) → fällt
━━━━━━━━━━━━━━━━━━━
⚠️ Wichtiger Hinweis für Anfänger:

Die ersten Minuten nach solchen News sind sehr volatil.

💡 Tipp:
Warte 10–15 Minuten, bis sich der Markt beruhigt hat, bevor du einen Trade eingehst.
━━━━━━━━━━━━━━━━━━━
📊 Kurze Analyse:
• Starke positive Abweichung
• Deutet auf positive Marktstimmung hin
• Kurzfristig: Momentum nach oben möglich
"""

        embed = discord.Embed(
            title="🚨 HIGH IMPACT – USD Fake Event (Test)",
            description="**TEST – nur zur Überprüfung**",
            color=0xff0000,
            timestamp=datetime.now(berlin_tz)
        )
        embed.add_field(name="📊 Marktanalyse", value=test_analysis, inline=False)
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
