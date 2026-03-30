import discord
import requests
import asyncio
import os

TOKEN = os.getenv("TOKEN")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

CHANNEL_ID = 1475125736665776128

client = discord.Client(intents=discord.Intents.default())
sent_news = set()

KEYWORDS = [
    "war", "attack", "missile", "china", "taiwan", "russia",
    "oil", "opec", "bank", "collapse", "crisis", "default",
    "inflation", "interest rate", "fed", "ecb",
    "bitcoin", "crypto", "stock", "nasdaq", "sp500",
    "gold", "silver"
]

def get_news():
    url = "https://newsapi.org/v2/top-headlines"

    params = {
        "language": "en",
        "pageSize": 20,
        "apiKey": NEWS_API_KEY
    }

    response = requests.get(url, params=params).json()
    return response.get("articles", [])

def is_important(title):
    title = title.lower()
    return any(word in title for word in KEYWORDS)

def analyze_news(title):
    t = title.lower()

    if any(x in t for x in ["war", "attack", "missile"]):
        return "🚨 EXTREME – Risk-Off (Gold 📈, Stocks 📉)"
    
    if any(x in t for x in ["bank", "collapse", "crisis"]):
        return "🏦 Banken Risiko – Märkte unsicher"
    
    if "oil" in t or "opec" in t:
        return "🛢️ Öl Bewegung erwartet"
    
    if any(x in t for x in ["fed", "interest rate"]):
        return "🏦 Zentralbank Einfluss"

    return "⚠️ Marktbewegung möglich"

async def news_loop():
    await client.wait_until_ready()
    channel = await client.fetch_channel(CHANNEL_ID)

    while not client.is_closed():
        articles = get_news()

        for article in articles:
            title = article["title"]
            url = article["url"]

            if title in sent_news:
                continue

            if not is_important(title):
                continue

            analysis = analyze_news(title)

            embed = discord.Embed(
                title="🌍 Breaking Market News",
                description=title,
                color=discord.Color.orange()
            )

            embed.add_field(name="📊 Analyse", value=analysis, inline=False)
            embed.add_field(name="🔗 Link", value=url, inline=False)

            await channel.send(embed=embed)

            sent_news.add(title)

        await asyncio.sleep(300)

@client.event
async def on_ready():
    print(f"News Bot online: {client.user}")
    client.loop.create_task(news_loop())

client.run(TOKEN)
