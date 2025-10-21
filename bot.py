import discord 
from discord import app_commands, ui, interaction
from discord.ext import tasks, commands
import deep_translator
import asyncio
import os
import random
import math as m
from dotenv import load_dotenv
import time
import aiohttp
import datetime
import openai
from openai import OpenAI
import yfinance as yf
import logging
import urllib.parse
from typing import Optional
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("The discord bot's token hasn't been found! Please set it up!")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
openai.api_key = OPENAI_API_KEY
openai_client = OpenAI()


OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")  
WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"
NEWS_API_KEY = 'e641f3d20f70427e8244ed5dc0016c52'
NEWS_API_URL = 'https://newsapi.org/v2/top-headlines'
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

answers = [
    "Yes 👍", "No 👎", "Maybe 🤔", "Absolutely ✅", "Definitely not ❌",
    "I don't think so 😅", "Ask again later ⏳", "Very likely 😎"
]

STOCKS = ["AAPL", "TSLA", "MSFT", "AMZN", "GOOG", "NVDA", "META", "NFLX", "INTC", "AMD"]

choices = ["Rock", "Paper", "Scissors"]

active_games = {}

class TicTacToeButton(discord.ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        if interaction.user != view.current_player:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
        if self.label != "\u200b":
            return
        self.label = view.symbols[view.turn]
        view.board[self.y][self.x] = view.symbols[view.turn]
        winner = view.check_winner()
        if winner:
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(content=f"🎉 {winner} wins!", view=view)
            view.stop()
        else:
            view.turn = 1 - view.turn
            view.current_player = view.players[view.turn]
            await interaction.response.edit_message(content=f"{view.current_player.mention}'s turn ({view.symbols[view.turn]})", view=view)

class TicTacToeView(discord.ui.View):
    def __init__(self, player1, player2):
        super().__init__()
        self.players = [player1, player2]
        self.current_player = player1
        self.turn = 0
        self.symbols = ["❌", "⭕"]
        self.board = [["" for _ in range(3)] for _ in range(3)]
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_winner(self):
        b = self.board
        # Check rows
        for row in b:
            if row[0] == row[1] == row[2] != "":
                return row[0]
        # Check columns
        for col in range(3):
            if b[0][col] == b[1][col] == b[2][col] != "":
                return b[0][col]
        # Check diagonals
        if b[0][0] == b[1][1] == b[2][2] != "":
            return b[0][0]
        if b[0][2] == b[1][1] == b[2][0] != "":
            return b[0][2]
        # Check draw
        if all(cell != "" for row in b for cell in row):
            return "No one"
        return None

class GuessNumberView(discord.ui.View):
    def __init__(self, target: int, max_value: int):
        super().__init__(timeout=300)
        self.target = target
        self.current_guess = max_value // 2  # Start in the middle for better UX
        self.max_value = max_value
        self.attempts = 0
        
    def _update_guess_buttons(self) -> None:
        self.increase.disabled = (self.current_guess >= self.max_value)
        self.decrease.disabled = (self.current_guess <= 1)
        
    def _get_guess_message(self) -> str:
        return f"**Current guess:** `{self.current_guess}`\n*Range: 1 - {self.max_value}*"
        
    def _get_result_message(self, guess: int) -> str:
        self.attempts += 1
        
        if guess < self.target:
            difference = self.target - guess
            hint = "🔼" if difference > 10 else "↗️"
            return f"**{guess}** is too low! {hint} (Attempt #{self.attempts})"
        elif guess > self.target:
            difference = guess - self.target
            hint = "🔽" if difference > 10 else "↘️"
            return f"**{guess}** is too high! {hint} (Attempt #{self.attempts})"
        else:
            return (f"🎉 **Congratulations {interaction.user.mention}!**\n"
                   f"You guessed the number **{self.target}** in {self.attempts} attempts! 🎯")

    @discord.ui.button(label="⬆️ Increase", style=discord.ButtonStyle.primary, row=0)
    async def increase(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_guess < self.max_value:
            self.current_guess += 1
            self._update_guess_buttons()
            await interaction.response.edit_message(
                content=self._get_guess_message(), 
                view=self
            )

    @discord.ui.button(label="⬇️ Decrease", style=discord.ButtonStyle.primary, row=0)
    async def decrease(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_guess > 1:
            self.current_guess -= 1
            self._update_guess_buttons()
            await interaction.response.edit_message(
                content=self._get_guess_message(), 
                view=self
            )

    @discord.ui.button(label="🎯 Submit Guess", style=discord.ButtonStyle.success, row=1)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        result_message = self._get_result_message(self.current_guess)
        
        if self.current_guess == self.target:
            # Game won - disable all buttons and remove view
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(content=result_message, view=self)
            self.stop()
        else:
            # Continue playing
            self._update_guess_buttons()
            await interaction.response.edit_message(content=result_message, view=self)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
            
        await interaction.response.edit_message(
            content=f"🚫 Game cancelled. The number was **{self.target}**.",
            view=self
        )
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        
        # Try to edit the message if it's still available
        try:
            await self.message.edit(
                content=f"⏰ Game timed out. The number was **{self.target}**.",
                view=self
            )
        except discord.NotFound:
            pass


last_action_time = {}

async def check_cooldown_manual(interaction: discord.Interaction, cooldown: int = 3) -> bool:
    user_id = interaction.user.id
    current_time = time.time()
    last_time = last_action_time.get(user_id, 0)
    remaining = cooldown - (current_time - last_time)
    
    if remaining > 0:
        await interaction.response.send_message(
            f"You're on cooldown! Please wait {remaining:.1f}s.",
            ephemeral=True
        )
        await asyncio.sleep(remaining)
        try:
            await interaction.delete_original_response()
        except:
            pass
        return False
    
    last_action_time[user_id] = current_time
    return True

async def make_request(url: str, headers: Optional[dict] = None, params: Optional[dict] = None) -> Optional[dict]:
    try:
        default_headers = {
            "User-Agent": "StudyBot/1.0 (Discord)"
        }
        if headers:
            default_headers.update(headers)
        async with aiohttp.ClientSession(headers=default_headers) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"HTTP {response.status} for URL: {url}")
                    return None
    except Exception as e:
        logger.error(f"Request failed for URL {url}: {e}")
        return None

def check_cooldown(cooldown: int = 3):
    def decorator(func):
        async def wrapper(interaction, *args, **kwargs):
            user_id = interaction.user.id
            current_time = time.time()
            last_time = last_action_time.get(user_id, 0)
            remaining = cooldown - (current_time - last_time)

            if remaining > 0:
                await interaction.response.send_message(
                    f"You're on cooldown! Please wait {remaining:.1f}s.",
                    ephemeral=True
                )
                await asyncio.sleep(remaining)
                try:
                    await interaction.delete_original_response()
                except:
                    pass
                return

            last_action_time[user_id] = current_time
            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

async def translate_message(message: str, target_language: str) -> str:
    try:
        translator = deep_translator.GoogleTranslator(target=target_language)
        translated = translator.translate(message)
        return translated
    except Exception as e:
        return f"Error during translation: {str(e)}"

@bot.tree.command(name="translate", description="Translate a word/text")
@app_commands.describe(message="The message to translate", target_language="The language to translate the message to")     
async def translate(interaction: discord.Interaction, message: str, target_language: str):
    if not await check_cooldown_manual(interaction):
        return
    
    translated_message = await translate_message(message, target_language)
    
    embed = discord.Embed(
        title="Translation Result",
        color=discord.Color.blue()
    )
    embed.add_field(name="Original Message", value=message, inline=False)
    embed.add_field(name="Translated To", value=f"{target_language.upper()}", inline=True)
    embed.add_field(name="Translation", value=translated_message, inline=False)
    embed.set_footer(text="Powered by deep_translator")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="Get the avatar of a user")
@app_commands.describe(user="The user to get the avatar of")
async def avatar(interaction: discord.Interaction, user: discord.User):
    if not await check_cooldown_manual(interaction):
        return
    
    embed = discord.Embed(
        title=f"{user.name}'s Avatar",
        color=discord.Color.blurple()
    )
    embed.set_image(url=user.display_avatar.url)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    latency = bot.latency * 1000  
    await interaction.response.send_message(f"Latency: {latency:.2f} ms")

@bot.tree.command(name="bible_lookup", description="Search up for a bible verse")
@app_commands.describe(reference="The Bible verse to lookup (e.g., John 3:16)")
async def bible_lookup(interaction: discord.Interaction, reference: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Bible lookup requested by {interaction.user.name}: {reference}")
    
    try:
        encoded_reference = urllib.parse.quote(reference)
        url = f"https://bible-api.com/{encoded_reference}"
        
        data = await make_request(url)
        if not data:
            await interaction.response.send_message("❌ Could not fetch Bible verse. Please check the reference format.")
            return
            
        if 'text' in data and 'reference' in data:
            embed = discord.Embed(
                title=f"📖 {data['reference']}",
                description=data['text'],
                color=discord.Color.blurple()
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched Bible verse: {data['reference']}")
        else:
            await interaction.response.send_message("❌ Sorry, I couldn't find that verse. Please check the reference format.")
            logger.warning(f"Invalid Bible API response for reference: {reference}")
            
    except Exception as e:
        logger.error(f"Bible lookup error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching the Bible verse.")
       
@bot.tree.command(name="get_random_bible_verse", description="Get a random verse from the bible")
async def bible_get(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Random Bible verse requested by {interaction.user.name}")
    
    try:
        url = "https://beta.ourmanna.com/api/v1/get/?format=json&order=random"
        data = await make_request(url)
        
        if not data:
            await interaction.response.send_message("❌ Could not fetch a random Bible verse. Please try again later.")
            return
            
        verse_info = data.get('verse', {}) if 'verse' in data else data.get('data', {}).get('verse', {})
        text = verse_info.get('details', {}).get('text') if 'details' in verse_info else verse_info.get('text')
        reference = verse_info.get('details', {}).get('reference') if 'details' in verse_info else verse_info.get('reference')
        if text and reference:
            embed = discord.Embed(
                title=f"📖 Random Bible Verse: {reference}",
                description=text,
                color=discord.Color.blurple()
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched random Bible verse: {reference}")
        else:
            await interaction.response.send_message("❌ Sorry, I couldn't fetch a random verse for you. It may be an issue with the bot or API.")
            logger.warning("Invalid Bible API response for random verse")
            
    except Exception as e:
        logger.error(f"Random Bible verse error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching a random Bible verse.")

@bot.tree.command(name="quran_lookup", description="Find a verse in the Qur'an")
@app_commands.describe(reference="The Quran reference (e.g., 2:255)")
async def quran_lookup(interaction: discord.Interaction, reference: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Quran lookup requested by {interaction.user.name}: {reference}")
    
    try:
        if ":" not in reference:
            await interaction.response.send_message("❌ Please use the format: Surah:Ayah (e.g., 2:255)")
            return
            
        surah, ayah = reference.split(":", 1)
        surah = int(surah)
        ayah = int(ayah)
        
        url = f"https://api.quran.com/api/v4/verses/by_key/{surah}:{ayah}?translations=20&fields=text_uthmani,translation"
        data = await make_request(url)
        
        if not data or 'verse' not in data:
            await interaction.response.send_message("❌ Could not fetch Quran verse. Please check the reference format.")
            return
            
        verse_data = data['verse']
        arabic_text = verse_data.get('text_uthmani', '')
        translation = verse_data.get('translation', {}).get('text', '')
        
        if not arabic_text and not translation:
            await interaction.response.send_message("❌ Verse not found. Please check the reference format.")
            return
            
        embed = discord.Embed(
            title=f"📖 Quran {reference}",
            color=discord.Color.green()
        )
        
        if arabic_text:
            embed.add_field(name="Arabic", value=arabic_text, inline=False)
        if translation:
            embed.add_field(name="English Translation", value=translation, inline=False)
            
        await interaction.response.send_message(embed=embed)
        logger.info(f"Successfully fetched Quran verse: {reference}")
            
    except ValueError:
        await interaction.response.send_message("❌ Invalid format. Please use: Surah:Ayah (e.g., 2:255)")
    except Exception as e:
        logger.error(f"Quran lookup error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching the Quran verse.")


@bot.tree.command(name="get_random_quran_verse", description="Get a random verse from the qur'an")
async def quran_get(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Random Quran verse requested by {interaction.user.name}")
    
    try:
        surah = random.randint(1, 114)
        ayah = random.randint(1, 286)
        reference = f"{surah}:{ayah}"
        
        url = f"https://api.quran.com/api/v4/verses/by_key/{surah}:{ayah}?translations=20&fields=text_uthmani,translation"
        data = await make_request(url)
        
        if not data or 'verse' not in data:
            await interaction.response.send_message("❌ Could not fetch a random Quran verse. Please try again later.")
            return
            
        verse_data = data['verse']
        arabic_text = verse_data.get('text_uthmani', '')
        translation = verse_data.get('translation', {}).get('text', '')
        
        if not arabic_text and not translation:
            await interaction.response.send_message("❌ Could not fetch a verse! Please try again.")
            return
            
        embed = discord.Embed(
            title=f"📖 Random Quran Verse: {reference}",
            color=discord.Color.green()
        )
        
        if arabic_text:
            embed.add_field(name="Arabic", value=arabic_text, inline=False)
        if translation:
            embed.add_field(name="English Translation", value=translation, inline=False)
            
        await interaction.response.send_message(embed=embed)
        logger.info(f"Successfully fetched random Quran verse: {reference}")
            
    except Exception as e:
        logger.error(f"Random Quran verse error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching a random Quran verse.")

@bot.tree.command(name="daily_verse", description="Get a daily verse from the Bible or Quran")
@app_commands.describe(source="Choose Bible or Quran")
async def daily_verse(interaction: discord.Interaction, source: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Daily verse request by {interaction.user.name}: {source}")
    
    try:
        source = source.lower()
        
        import datetime
        today = datetime.date.today()
        seed = hash(str(today) + source) % 1000000
        random.seed(seed)
        
        if source == "bible":
            books = ["John", "Genesis", "Psalms", "Proverbs", "Matthew", "Luke", "Romans", "Ephesians", "Philippians", "Colossians"]
            book = random.choice(books)
            chapter = random.randint(1, 50)
            verse = random.randint(1, 30)
            reference = f"{book} {chapter}:{verse}"
            
            encoded_reference = urllib.parse.quote(reference)
            url = f"https://bible-api.com/{encoded_reference}"
            
            data = await make_request(url)
            if not data:
                await interaction.response.send_message("❌ Could not fetch daily Bible verse. Please try again later.")
                return
                
            if 'text' in data and 'reference' in data:
                embed = discord.Embed(
                    title=f"📖 Daily Bible Verse - {data['reference']}",
                    description=data['text'],
                    color=discord.Color.blurple()
                )
                embed.set_footer(text=f"Daily verse for {today.strftime('%B %d, %Y')}")
                await interaction.response.send_message(embed=embed)
                logger.info(f"Successfully fetched daily Bible verse: {data['reference']}")
            else:
                await interaction.response.send_message("❌ Could not fetch a Bible verse.")
                logger.warning(f"Invalid Bible API response for daily verse: {reference}")
                
        elif source == "quran":
            surah = random.randint(1, 114)
            ayah = random.randint(1, 286)
            reference = f"{surah}:{ayah}"
            
            url = f"https://api.quran.com/api/v4/verses/by_key/{surah}:{ayah}?translations=20&fields=text_uthmani,translation"
            data = await make_request(url)
            
            if not data or 'verse' not in data:
                await interaction.response.send_message("❌ Could not fetch daily Quran verse. Please try again later.")
                return
                
            verse_data = data['verse']
            arabic_text = verse_data.get('text_uthmani', '')
            translation = verse_data.get('translation', {}).get('text', '')
            
            if not arabic_text and not translation:
                await interaction.response.send_message("❌ Could not fetch a Quran verse.")
                return
                
            embed = discord.Embed(
                title=f"📖 Daily Quran Verse - {reference}",
                color=discord.Color.green()
            )
            
            if arabic_text:
                embed.add_field(name="Arabic", value=arabic_text, inline=False)
            if translation:
                embed.add_field(name="English Translation", value=translation, inline=False)
                
            embed.set_footer(text=f"Daily verse for {today.strftime('%B %d, %Y')}")
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched daily Quran verse: {reference}")
        else:
            await interaction.response.send_message("❌ Please choose either 'Bible' or 'Quran'.")
            logger.warning(f"Invalid source for daily verse: {source}")
            
    except Exception as e:
        logger.error(f"Daily verse command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching the daily verse.")

class RPSView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30) 

    @discord.ui.button(label="Rock", style=discord.ButtonStyle.primary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "Rock")

    @discord.ui.button(label="Paper", style=discord.ButtonStyle.success)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "Paper")

    @discord.ui.button(label="Scissors", style=discord.ButtonStyle.danger)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "Scissors")

    async def play(self, interaction: discord.Interaction, user_choice: str):
        bot_choice = random.choice(choices)
        if user_choice == bot_choice:
            result = "It's a tie!"
        elif (user_choice == "Rock" and bot_choice == "Scissors") or \
             (user_choice == "Paper" and bot_choice == "Rock") or \
             (user_choice == "Scissors" and bot_choice == "Paper"):
            result = "You won!"
        else:
            result = "You have lost! Try again"

        await interaction.response.edit_message(
            content=f"Your choice: {user_choice}\nBot choice: {bot_choice}\n{result}",
            view=None
        )

@bot.tree.command(name="rps", description="Play Rock-Paper-Scissors with the bot!")
async def rps(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    await interaction.response.send_message("Choose your move:", view=RPSView())       

@bot.tree.command(name="8ball", description="Ask the magic 8ball a question!")
@app_commands.describe(question="The question you want to ask")
async def eight_ball(interaction: discord.Interaction, question: str):
    if not await check_cooldown_manual(interaction):
        return
    response = random.choice(answers)
    await interaction.response.send_message(f"🎱 Question: {question}\nAnswer: {response}")    

@bot.tree.command(name="coinflip", description="Flip a coin!")
async def coinflip(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    result = random.choice(["Heads 🪙", "Tails 🪙"])
    await interaction.response.send_message(f"And the winner is 🥁: {result}")    

@bot.tree.command(name="dadjoke", description="Get a random dad joke!")
async def dadjoke(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Dad joke request by {interaction.user.name}")
    
    try:
        headers = {"Accept": "application/json"}
        data = await make_request("https://icanhazdadjoke.com/", headers=headers)
        
        if data and 'joke' in data:
            embed = discord.Embed(
                title="😂 Dad Joke",
                description=data['joke'],
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            logger.info("Successfully fetched dad joke")
        else:
            await interaction.response.send_message("❌ Couldn't fetch a dad joke 😢")
            logger.warning("Failed to fetch dad joke")
            
    except Exception as e:
        logger.error(f"Dad joke command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching a dad joke.")  

@bot.tree.command(name="recent_news", description="Fetch the latest news headlines")
@app_commands.describe(country="Country code (e.g., 'us' for United States)")
async def news(interaction: discord.Interaction, country: str = 'us'):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"News request by {interaction.user.name}: {country}")
    
    try:
        params = {
            'country': country,
            'apiKey': NEWS_API_KEY
        }
        
        data = await make_request(NEWS_API_URL, params=params)
        if not data:
            await interaction.response.send_message("❌ Could not fetch news. Please try again later.")
            return

        if data.get('status') == 'ok' and data.get('totalResults', 0) > 0:
            articles = data['articles'][:5]
            embed = discord.Embed(
                title=f"📰 Latest News ({country.upper()})",
                color=discord.Color.red()
            )
            
            for i, article in enumerate(articles, 1):
                title = article.get('title', 'No title')[:100]
                description = article.get('description', 'No description')[:200]
                url = article.get('url', '#')
                
                embed.add_field(
                    name=f"{i}. {title}",
                    value=f"{description}\n[Read more]({url})",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched {len(articles)} news articles for {country}")
        else:
            await interaction.response.send_message("❌ No news found or invalid country code.")
            logger.warning(f"No news found for country: {country}")
            
    except Exception as e:
        logger.error(f"News command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching news.")

@bot.tree.command(name="weather", description="Get the current weather in a city")
@app_commands.describe(city="The city you want to check the weather for")
async def weather(interaction: discord.Interaction, city: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Weather request by {interaction.user.name}: {city}")
    
    try:
        params = {
            "q": city,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric"
        }
        
        data = await make_request(WEATHER_URL, params=params)
        if not data:
            await interaction.response.send_message(f"❌ Could not find weather for `{city}`. Please check the city name.")
            return

        if data.get("cod") != 200:
            await interaction.response.send_message(f"❌ Could not find weather for `{city}`. Please check the city name.")
            logger.warning(f"Weather API error for city: {city}")
            return

        city_name = data["name"]
        country = data["sys"]["country"]
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        weather_desc = data["weather"][0]["description"].title()
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]

        embed = discord.Embed(
            title=f"🌤️ Weather in {city_name}, {country}",
            color=discord.Color.blue()
        )
        embed.add_field(name="🌡️ Temperature", value=f"{temp}°C (Feels like {feels_like}°C)", inline=True)
        embed.add_field(name="🌥️ Condition", value=weather_desc, inline=True)
        embed.add_field(name="💧 Humidity", value=f"{humidity}%", inline=True)
        embed.add_field(name="💨 Wind Speed", value=f"{wind_speed} m/s", inline=True)

        await interaction.response.send_message(embed=embed)
        logger.info(f"Successfully fetched weather for {city_name}, {country}")
        
    except Exception as e:
        logger.error(f"Weather command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching weather data.")

@bot.tree.command(name="remind", description="Set a reminder")
@app_commands.describe(time="Time in seconds", message="Message for the reminder")
async def remind(interaction: discord.Interaction, time: int, message: str):
    if not await check_cooldown_manual(interaction):
        return
    await interaction.response.send_message(f"⏰ I will remind you in {time} seconds, {interaction.user.mention}!")
    await asyncio.sleep(time)
    await interaction.followup.send(f"⏰ {interaction.user.mention} Reminder: {message}", allowed_mentions=discord.AllowedMentions(users=True))    

@bot.tree.command(name="time", description="Get the current time in a city or region")
@app_commands.describe(city="Enter a city or timezone (e.g., London, New_York, Tokyo)")
async def time_cmd(interaction: discord.Interaction, city: str):
    if not await check_cooldown_manual(interaction):
        return

    await interaction.response.defer()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://worldtimeapi.org/api/timezone") as r:
                zones = await r.json()

            matched = [z for z in zones if city.lower() in z.lower()]
            if not matched:
                await interaction.followup.send("❌ Timezone not found. Try something like `Europe/London` or `New_York`.")
                return

            zone = matched[0]
            async with session.get(f"http://worldtimeapi.org/api/timezone/{zone}") as r:
                data = await r.json()

        datetime_str = data["datetime"]
        dt = datetime.datetime.fromisoformat(datetime_str[:-6])
        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")

        embed = discord.Embed(
            title=f"🕒 Current Time in {zone.replace('_', ' ')}",
            description=f"**{formatted_time}**",
            color=discord.Color.blurple()
        )
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching time: {e}")

@bot.tree.command(name="stock", description="Get the latest stock price and chart")
@app_commands.describe(symbol="Stock symbol (e.g., AAPL, TSLA)")
async def stock(interaction: discord.Interaction, symbol: str):
    if not await check_cooldown_manual(interaction):
        return

    try:
        stock_info = yf.Ticker(symbol)
        data = stock_info.history(period="7d")
        if data.empty:
            await interaction.response.send_message("Invalid stock symbol or no data available.")
            return

        latest_price = data['Close'].iloc[-1]
        prev_price = data['Close'].iloc[-2] if len(data) > 1 else latest_price
        change = latest_price - prev_price
        change_pct = (change / prev_price) * 100 if prev_price != 0 else 0

        emoji = "📈" if change > 0 else "📉" if change < 0 else "➖"
        message = f"{emoji} **{symbol.upper()}** latest price: ${latest_price:.2f} ({change:+.2f}, {change_pct:+.2f}%)"

        plt.figure(figsize=(6, 3))
        plt.plot(data.index, data['Close'], marker='o', linestyle='-', color='blue')
        plt.title(f"{symbol.upper()} Price - Last 7 Days")
        plt.xlabel("Date")
        plt.ylabel("Price ($)")
        plt.grid(True)
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format="PNG")
        buf.seek(0)
        plt.close()

        embed = discord.Embed(
            title=f"💹 {symbol.upper()} Stock Info",
            description=message,
            color=discord.Color.green() if change > 0 else discord.Color.red()
        )
        file = discord.File(buf, filename="stock.png")
        embed.set_image(url="attachment://stock.png")
        await interaction.response.send_message(file=file, embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"Error fetching stock data: {e}")  

@bot.tree.command(name="top_gainers", description="Show the top 5 gaining stocks today")
async def top_gainers(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return

    await interaction.response.defer()

    stock_changes = []
    try:
        for symbol in STOCKS:
            data = yf.Ticker(symbol).history(period="2d")
            if len(data) < 2:
                continue
            last = data['Close'].iloc[-1]
            prev = data['Close'].iloc[-2]
            pct_change = ((last - prev) / prev) * 100
            stock_changes.append((symbol, pct_change))

        if not stock_changes:
            await interaction.followup.send("❌ Could not fetch stock data.")
            return

        gainers = sorted(stock_changes, key=lambda x: x[1], reverse=True)[:5]
        width, height = 400, 150
        img = Image.new("RGB", (width, height), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        draw.text((10, 10), "📈 Top 5 Gainers", fill="green", font=font)

        for i, (symbol, pct) in enumerate(gainers):
            draw.text((10, 30 + i*20), f"{symbol}: {pct:+.2f}%", fill="white", font=font)

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        embed = discord.Embed(
            title="💹 Top 5 Gainers Today",
            color=discord.Color.green()
        )
        file = discord.File(buf, filename="gainers.png")
        embed.set_image(url="attachment://gainers.png")
        await interaction.followup.send(file=file, embed=embed)

    except Exception as e:
        await interaction.followup.send(f"Error fetching top gainers: {e}")
@bot.tree.command(name="crypto", description="Get cryptocurrency price")
@app_commands.describe(coin="Cryptocurrency ID (e.g., bitcoin, ethereum)")
async def crypto(interaction: discord.Interaction, coin: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Crypto request by {interaction.user.name}: {coin}")
    
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin.lower()}&vs_currencies=usd"
        data = await make_request(url)
        
        if not data:
            await interaction.response.send_message("❌ Could not fetch crypto data. Please try again later.")
            return
            
        if coin.lower() not in data:
            await interaction.response.send_message("❌ Invalid coin name or not found. Please check the cryptocurrency ID.")
            logger.warning(f"Crypto not found: {coin}")
            return
            
        price = data[coin.lower()]['usd']
        embed = discord.Embed(
            title=f"💰 {coin.capitalize()} Price",
            description=f"**Current Price:** ${price:,.2f}",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"Successfully fetched crypto price for {coin}: ${price}")
        
    except Exception as e:
        logger.error(f"Crypto command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching crypto data.")        

@bot.tree.command(name="wiki", description="Get a summary from Wikipedia")
@app_commands.describe(topic="The topic to search on Wikipedia")
async def wiki(interaction: discord.Interaction, topic: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Wiki request by {interaction.user.name}: {topic}")
    
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(topic.replace(' ', '_'))}?redirect=true"
        data = await make_request(url)
        
        if not data:
            await interaction.response.send_message("❌ Could not fetch Wikipedia data. Please try again later.")
            return
            
        if "extract" in data:
            title = data.get('title', topic)
            extract = data.get('extract', 'No summary available')
            
            if len(extract) > 2000:
                extract = extract[:2000] + "..."
                
            embed = discord.Embed(
                title=f"📚 {title}",
                description=extract,
                color=discord.Color.blue()
            )
            
            if 'thumbnail' in data:
                embed.set_thumbnail(url=data['thumbnail']['source'])
                
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched Wikipedia summary for: {title}")
        else:
            search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(topic)}&limit=1&namespace=0&format=json"
            sdata = await make_request(search_url)
            if sdata and len(sdata) >= 2 and sdata[1]:
                new_topic = sdata[1][0]
                return await wiki(interaction, new_topic)
            await interaction.response.send_message("❌ No summary found for that topic.")
            logger.warning(f"No Wikipedia summary found for: {topic}")
            
    except Exception as e:
        logger.error(f"Wiki command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching Wikipedia data.")     

@bot.tree.command(name="randomcolor", description="Get a random color hex id")
async def randomcolor(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    color = f"#{random.randint(0, 0xFFFFFF):06X}"
    await interaction.response.send_message(f"🎨 Random Color: {color}")

@bot.tree.command(name="joke_programming", description="Get a random programming joke")
async def joke_programming(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Programming joke request by {interaction.user.name}")
    
    try:
        data = await make_request("https://v2.jokeapi.dev/joke/Programming?type=single")
        
        if data and 'joke' in data:
            embed = discord.Embed(
                title="😂 Programming Joke",
                description=data['joke'],
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
            logger.info("Successfully fetched programming joke")
        else:
            await interaction.response.send_message("❌ Couldn't fetch a programming joke 😢")
            logger.warning("Failed to fetch programming joke")
            
    except Exception as e:
        logger.error(f"Programming joke command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching a programming joke.")

@bot.tree.command(name="joke_general", description="Get a random general joke")
async def joke_general(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"General joke request by {interaction.user.name}")
    
    try:
        data = await make_request("https://v2.jokeapi.dev/joke/Any?type=single")
        
        if data and 'joke' in data:
            embed = discord.Embed(
                title="😂 Random Joke",
                description=data['joke'],
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=embed)
            logger.info("Successfully fetched general joke")
        else:
            await interaction.response.send_message("❌ Couldn't fetch a joke 😢")
            logger.warning("Failed to fetch general joke")
            
    except Exception as e:
        logger.error(f"General joke command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching a joke.")

@bot.tree.command(name="fact", description="Get a random fun fact")
async def fact(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Fun fact request by {interaction.user.name}")
    
    try:
        data = await make_request("https://uselessfacts.jsph.pl/random.json?language=en")
        
        if data and 'text' in data:
            embed = discord.Embed(
                title="🧠 Fun Fact",
                description=data['text'],
                color=discord.Color.teal()
            )
            await interaction.response.send_message(embed=embed)
            logger.info("Successfully fetched fun fact")
        else:
            await interaction.response.send_message("❌ Couldn't fetch a fun fact 😢")
            logger.warning("Failed to fetch fun fact")
            
    except Exception as e:
        logger.error(f"Fact command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching a fun fact.")

@bot.tree.command(name="define", description="Get the definition of a word using an API")
@app_commands.describe(word="The word to define")
async def define(interaction: discord.Interaction, word: str):
    if not await check_cooldown_manual(interaction):
        return

    logger.info(f"Define request by {interaction.user.name}: {word}")

    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ Could not fetch definition. Please try again later.")
                    return
                data = await resp.json()

        if isinstance(data, list) and len(data) > 0 and "meanings" in data[0]:
            definition = data[0]["meanings"][0]["definitions"][0]["definition"]
            embed = discord.Embed(
                title=f"📖 Definition of {word}",
                description=definition,
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched definition for: {word}")
        else:
            await interaction.response.send_message(f"❌ No definition found for `{word}`.")
            logger.warning(f"No definition found for: {word}")

    except Exception as e:
        logger.error(f"Define command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching the definition.")

@bot.tree.command(name="math", description="Evaluate a mathematical expression")
@app_commands.describe(expression="Expression to calculate (e.g., 2+3*4)")
async def math_cmd(interaction: discord.Interaction, expression: str):
    if not await check_cooldown_manual(interaction):
        return
    try:
        allowed_names = {k: getattr(m, k) for k in dir(m) if not k.startswith("__")}
        allowed_names.update({"abs": abs, "round": round})
        result = eval(expression, {"__builtins__": None}, allowed_names)
        await interaction.response.send_message(f"🧮 {expression} = {result}")
    except Exception as e:
        await interaction.response.send_message(f"Invalid expression: {e}")

@bot.tree.command(name="guessnumber", description="Guess a number between 1 and max using buttons")
@app_commands.describe(max_value="Maximum number (default 100)")
async def guessnumber(interaction: discord.Interaction, max_value: int = 100):
    if not await check_cooldown_manual(interaction):
        return
    target_number = random.randint(1, max_value)
    view = GuessNumberView(target=target_number, max_value=max_value)
    await interaction.response.send_message(f"🔢 Guess a number between 1 and {max_value}!", view=view)

@bot.tree.command(name="anime", description="Fetch anime info from MyAnimeList")
@app_commands.describe(title="Title of the anime")
async def anime(interaction: discord.Interaction, title: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Anime request by {interaction.user.name}: {title}")
    
    try:
        url = f"https://api.jikan.moe/v4/anime?q={urllib.parse.quote(title)}&limit=1"
        data = await make_request(url)
        
        if not data:
            await interaction.response.send_message("❌ Could not fetch anime data. Please try again later.")
            return
            
        if data.get("data") and len(data["data"]) > 0:
            anime_data = data["data"][0]
            embed = discord.Embed(
                title=f"📺 {anime_data.get('title', 'Unknown Title')}",
                color=discord.Color.pink()
            )
            
            embed.add_field(name="Rating", value=f"{anime_data.get('score', 'N/A')}/10", inline=True)
            embed.add_field(name="Type", value=anime_data.get('type', 'N/A'), inline=True)
            embed.add_field(name="Episodes", value=anime_data.get('episodes', 'N/A'), inline=True)
            embed.add_field(name="Status", value=anime_data.get('status', 'N/A'), inline=True)
            embed.add_field(name="Aired", value=anime_data.get('aired', {}).get('string', 'N/A'), inline=True)
            embed.add_field(name="Genres", value=", ".join([genre['name'] for genre in anime_data.get('genres', [])[:3]]), inline=True)
            
            if anime_data.get('url'):
                embed.add_field(name="Link", value=f"[View on MyAnimeList]({anime_data['url']})", inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched anime info for: {anime_data.get('title')}")
        else:
            await interaction.response.send_message("❌ Anime not found.")
            logger.warning(f"No anime found for: {title}")
            
    except Exception as e:
        logger.error(f"Anime command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching anime information.")

@bot.tree.command(name="manga", description="Fetch manga info from MyAnimeList")
@app_commands.describe(title="Title of the manga")
async def manga(interaction: discord.Interaction, title: str):
    if not await check_cooldown_manual(interaction):
        return
    
    logger.info(f"Manga request by {interaction.user.name}: {title}")
    
    try:
        url = f"https://api.jikan.moe/v4/manga?q={urllib.parse.quote(title)}&limit=1"
        data = await make_request(url)
        
        if not data:
            await interaction.response.send_message("❌ Could not fetch manga data. Please try again later.")
            return
            
        if data.get("data") and len(data["data"]) > 0:
            manga_data = data["data"][0]
            embed = discord.Embed(
                title=f"📚 {manga_data.get('title', 'Unknown Title')}",
                color=discord.Color.orange()
            )
            
            embed.add_field(name="Chapters", value=manga_data.get('chapters', 'N/A'), inline=True)
            embed.add_field(name="Volumes", value=manga_data.get('volumes', 'N/A'), inline=True)
            embed.add_field(name="Score", value=f"{manga_data.get('score', 'N/A')}/10", inline=True)
            embed.add_field(name="Status", value=manga_data.get('status', 'N/A'), inline=True)
            embed.add_field(name="Published", value=manga_data.get('published', {}).get('string', 'N/A'), inline=True)
            embed.add_field(name="Genres", value=", ".join([genre['name'] for genre in manga_data.get('genres', [])[:3]]), inline=True)
            
            if manga_data.get('url'):
                embed.add_field(name="Link", value=f"[View on MyAnimeList]({manga_data['url']})", inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched manga info for: {manga_data.get('title')}")
        else:
            await interaction.response.send_message("❌ Manga not found.")
            logger.warning(f"No manga found for: {title}")
            
    except Exception as e:
        logger.error(f"Manga command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching manga information.")

@bot.tree.command(name="tic-tac-toe", description="Play Tic-Tac-Toe with a friend")
@app_commands.describe(opponent="User to play with")
async def tictactoe(interaction: discord.Interaction, opponent: discord.User):
    if not await check_cooldown_manual(interaction):
        return
    if opponent.bot:
        await interaction.response.send_message("You cannot play with a bot!")
        return
    view = TicTacToeView(interaction.user, opponent)
    await interaction.response.send_message(f"{interaction.user.mention} vs {opponent.mention} - {interaction.user.mention}'s turn (❌)", view=view)

@bot.tree.command(name="lyrics", description="Get lyrics for a song")
@app_commands.describe(song="Song title to search, format: Artist - Title")
async def lyrics(interaction: discord.Interaction, song: str):
    if not await check_cooldown_manual(interaction):
        return

    logger.info(f"Lyrics request by {interaction.user.name}: {song}")

    # Expecting format "Artist - Title"
    if " - " not in song:
        await interaction.response.send_message("❌ Please use the format: Artist - Title")
        return

    artist, title = map(str.strip, song.split(" - ", 1))
    url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ Could not fetch lyrics. Please try again later.")
                    return
                data = await resp.json()

        if "lyrics" in data and data["lyrics"].strip():
            text = data["lyrics"]
            if len(text) > 2000:
                text = text[:2000] + "..."
            
            embed = discord.Embed(
                title=f"🎵 Lyrics for {artist} - {title}",
                description=text,
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"Successfully fetched lyrics for: {song}")
        else:
            await interaction.response.send_message("❌ Lyrics not found.")
            logger.warning(f"No lyrics found for: {song}")

    except Exception as e:
        logger.error(f"Lyrics command error: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching lyrics.")

@bot.tree.command(name="top_losers", description="Show the top 5 losing stocks today")
async def top_losers(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return

    await interaction.response.defer()
    stock_changes = []
    try:
        for symbol in STOCKS:
            data = yf.Ticker(symbol).history(period="2d")
            if len(data) < 2:
                continue
            last = data['Close'].iloc[-1]
            prev = data['Close'].iloc[-2]
            pct_change = ((last - prev) / prev) * 100
            stock_changes.append((symbol, pct_change))

        if not stock_changes:
            await interaction.followup.send("❌ Could not fetch stock data.")
            return

        losers = sorted(stock_changes, key=lambda x: x[1])[:5]
        width, height = 400, 150
        img = Image.new("RGB", (width, height), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        draw.text((10, 10), "📉 Top 5 Losers", fill="red", font=font)
        for i, (symbol, pct) in enumerate(losers):
            draw.text((10, 30 + i * 20), f"{symbol}: {pct:+.2f}%", fill="white", font=font)

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        embed = discord.Embed(
            title="💹 Top 5 Losers Today",
            color=discord.Color.red()
        )
        file = discord.File(buf, filename="losers.png")
        embed.set_image(url="attachment://losers.png")
        await interaction.followup.send(file=file, embed=embed)

    except Exception as e:
        await interaction.followup.send(f"Error fetching top losers: {e}")
@bot.tree.command(name="userinfo", description="Show information about a user")
@app_commands.describe(user="User to lookup; defaults to yourself")
async def userinfo(interaction: discord.Interaction, user: Optional[discord.User] = None):
    if not await check_cooldown_manual(interaction):
        return
    user = user or interaction.user
    embed = discord.Embed(title=f"👤 User Info: {user}", color=discord.Color.blurple())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=str(user.id), inline=True)
    embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)
    embed.add_field(name="Created", value=discord.utils.format_dt(user.created_at, style='R'), inline=True)
    if isinstance(interaction.user, discord.Member):
        member = interaction.guild.get_member(user.id)
        if member:
            embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, style='R'), inline=True)
            roles = ", ".join(role.mention for role in member.roles if role.name != "@everyone") or "None"
            embed.add_field(name="Roles", value=roles[:1024], inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Show information about this server")
async def serverinfo(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    guild = interaction.guild
    if not guild:
        return await interaction.response.send_message("This command can only be used in a server.")
    embed = discord.Embed(title=f"🏰 Server Info: {guild.name}", color=discord.Color.green())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="ID", value=str(guild.id), inline=True)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style='R'), inline=True)
    embed.add_field(name="Owner", value=str(guild.owner), inline=True)
    embed.add_field(name="Channels", value=f"Text: {len(guild.text_channels)} | Voice: {len(guild.voice_channels)}", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    if not await check_cooldown_manual(interaction):
        return
    
    embed = discord.Embed(
        title="🤖 StudyBot Commands Help",
        description="A comprehensive Discord bot with AI, games, utilities, and more This was made for the Interschool Project!",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="🌐 Language & Translation",
        value="`/translate` - Translate text to any language\n`/define` - Get word definitions from dictionary",
        inline=False
    )
    
    embed.add_field(
        name="📖 Religious & Spiritual",
        value="`/bible_lookup` - Search specific Bible verses\n`/get_random_bible_verse` - Get random Bible verse\n`/quran_lookup` - Search Quran verses\n`/get_random_quran_verse` - Get random Quran verse\n`/daily_verse` - Daily verse from Bible or Quran",
        inline=False
    )
    
    embed.add_field(
        name="🎮 Games & Entertainment",
        value="`/rps` - Rock Paper Scissors with the bot\n`/8ball` - Ask the magic 8-ball\n`/coinflip` - Flip a coin\n`/tic-tac-toe` - Play Tic-Tac-Toe with friends\n`/guessnumber` - Interactive number guessing game",
        inline=False
    )
    
    embed.add_field(
        name="📊 Financial & Market Data",
        value="`/stock` - Get stock prices and charts\n`/crypto` - Cryptocurrency prices\n`/top_gainers` - Top 5 gaining stocks today\n`/top_losers` - Top 5 losing stocks today",
        inline=False
    )
    
    embed.add_field(
        name="🌤️ Information & News",
        value="`/weather` - Current weather for any city\n`/recent_news` - Latest news headlines\n`/wiki` - Wikipedia article summaries\n`/time` - Current time in any timezone",
        inline=False
    )
    
    embed.add_field(
        name="🎭 Fun & Jokes",
        value="`/dadjoke` - Random dad jokes\n`/joke_programming` - Programming jokes\n`/joke_general` - General jokes\n`/fact` - Random fun facts\n`/randomcolor` - Random color hex codes",
        inline=False
    )
    
    embed.add_field(
        name="📺 Media & Culture",
        value="`/anime` - Anime information from MyAnimeList\n`/manga` - Manga information from MyAnimeList\n`/lyrics` - Song lyrics search",
        inline=False
    )
    
    embed.add_field(
        name="👤 User & Server Info",
        value="`/userinfo` - Detailed user information\n`/serverinfo` - Server information\n`/avatar` - Get user avatar\n`/ping` - Check bot latency",
        inline=False
    )
    
    embed.add_field(
        name="🔧 Utilities",
        value="`/math` - Calculate mathematical expressions\n`/remind` - Set personal reminders",
        inline=False
    )
    
    embed.set_footer(text="All commands have a 3-second cooldown • Use /help to see this again • Bot made with ❤️")
    
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    synced = await bot.tree.sync()  
    print(f"Commands synced: {len(synced)}")
    print(f"Logged in as {bot.user}")

bot.run(BOT_TOKEN)


