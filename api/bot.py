import asyncio
import random
import os
import json
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InputMediaPhoto
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from io import BytesIO

# Load tokens from environment variables
load_dotenv()

BASE_URL = "https://api.themoviedb.org/3"
TMDB_TOKEN = os.getenv("TMDB_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

headers = {
    "Authorization": f"Bearer {TMDB_TOKEN}"
}

# --- TMDB API functions ---
def fetch_movie_details(movie_id):
    """Fetches movie details from TMDB API."""
    try:
        response = requests.get(
            f"{BASE_URL}/movie/{movie_id}?language=uk-UA",
            headers=headers,
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie details: {e}")
        return None

def fetch_movie_cast(movie_id):
    """Fetches movie cast from TMDB API."""
    try:
        response = requests.get(
            f"{BASE_URL}/movie/{movie_id}/credits?language=uk-UA",
            headers=headers,
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie cast: {e}")
        return None

def fetch_top_rated_movies(page=1):
    """Fetches top-rated movies from TMDB API."""
    try:
        response = requests.get(
            f"{BASE_URL}/movie/top_rated?language=uk-UA&page={page}",
            headers=headers,
            timeout=5
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching top-rated movies: {e}")
        return []

def get_random_movie_info():
    """Gets a random movie from the top-rated list and fetches its details."""
    try:
        # Since Vercel is stateless, we don't save IDs.
        # We can fetch a random page from 1 to 5 to get a good variety.
        random_page = random.randint(1, 5)
        movies = fetch_top_rated_movies(page=random_page)
        
        if not movies:
            return None

        movie = random.choice(movies)
        movie_id = movie.get('id')
        
        details = fetch_movie_details(movie_id)
        cast = fetch_movie_cast(movie_id)

        if not details or not cast:
            return None

        # Process genres, limit to 5
        genres = [g['name'] for g in details.get('genres', [])][:5]
        genres_str = ", ".join(genres) if genres else "Невідомий жанр"

        # Process actors, limit to 4
        actors = [a['name'] for a in cast.get('cast', [])][:4]
        actors_str = ", ".join(actors) if actors else "Інформація про акторів відсутня"
        
        caption = (
            f"**{details.get('title', '?')}** ({details.get('release_date', '?')[:4]})\n\n"
            f"⭐️ Рейтинг: **{details.get('vote_average', '?'):.1f}/10**\n\n"
            f"🎭 Жанр: **{genres_str}**\n\n"
            f"👥 Актори: **{actors_str}**\n\n"
            f"📝 {details.get('overview', 'Опис відсутній')}"
        )

        poster_url = f"https://image.tmdb.org/t/p/w500{details['poster_path']}" if details.get('poster_path') else None
        
        return {
            'caption': caption,
            'poster_url': poster_url
        }

    except Exception as e:
        print(f"An error occurred in get_random_movie_info: {e}")
        return None

# --- Bot setup and handlers ---
bot = Bot(token=TELEGRAM_TOKEN, parse_mode="Markdown")
dp = Dispatcher()

@dp.message(Command("start"))
async def handle_start(message: types.Message):
    """Handles the /start command."""
    await message.answer(
        "👋 Привіт! Я бот, який рекомендує фільми.\n\n"
        "🎬 Використай команду /movie щоб отримати рекомендацію."
    )
    print(f"Handled /start command for chat_id: {message.chat.id}")

@dp.message(Command("movie"))
async def handle_movie(message: types.Message):
    """Handles the /movie command to send a random movie."""
    await bot.send_chat_action(message.chat.id, "typing")
    movie_info = get_random_movie_info()

    if movie_info and movie_info['poster_url']:
        try:
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=movie_info['poster_url'],
                caption=movie_info['caption']
            )
        except Exception as e:
            print(f"Error sending photo, sending text instead: {e}")
            await bot.send_message(
                chat_id=message.chat.id,
                text=movie_info['caption']
            )
    elif movie_info:
        await bot.send_message(
            chat_id=message.chat.id,
            text=movie_info['caption']
        )
    else:
        await message.answer("😔 На жаль, не вдалося знайти фільм. Спробуйте ще раз!")
    
    print(f"Sent movie for chat_id: {message.chat.id}")

@dp.message()
async def handle_unknown_message(message: types.Message):
    """Handles any other message not matching a command."""
    await message.answer(
        "🤔 Я розумію лише команди.\n\n"
        "Спробуй /start або /movie."
    )
    print(f"Handled unknown message for chat_id: {message.chat.id}")

# --- Flask server for webhook ---
app = Flask(__name__)

@app.route("/", methods=["GET"])
def hello_world():
    """Simple route for Vercel deployment check."""
    return "<h1>Movie Bot is running!</h1>"

@app.route("/webhook", methods=["POST"])
async def webhook():
    """Receives and processes Telegram updates."""
    update = request.get_json()
    if not update:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    try:
        # Create an update object from the JSON data
        telegram_update = types.Update.model_validate(update)
        # Pass the update to the aiogram dispatcher
        await dp.feed_update(bot, telegram_update)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error processing update: {e}")
        return jsonify({"status": "error", "message": "Failed to process update"}), 500

def set_webhook_url():
    """Sets the webhook URL on Telegram."""
    webhook_url = f"https://telegram-movie-bot.vercel.app/webhook"
    response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook", json={"url": webhook_url})
    print("Webhook setup response:", response.json())

# This block is for Vercel deployment
if __name__ == "__main__":
    # In a serverless environment, we only need to set the webhook once
    # and then the Flask app will handle requests.
    # Vercel provides its own server, so we don't run app.run()
    # For local testing, you can uncomment the line below.
    # set_webhook_url()
    # app.run(debug=True, port=5000)
    pass

