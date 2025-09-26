import asyncio
import random
import os
import json
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InputMediaPhoto
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, time
from dotenv import load_dotenv

# Завантажуємо токени з env
load_dotenv()

BASE_URL = "https://api.themoviedb.org/3"
TMDB_TOKEN = os.getenv("TMDB_TOKEN")
headers = {
    "Authorization": f"Bearer {TMDB_TOKEN}"
}

# --- Зберігання стану ---
sent_movie_ids = []
MAX_SENT_IDS = 1000
current_page = 1 # Додаємо відстеження поточної сторінки

def save_sent_ids():
    """Зберігає список відправлених ID у файл."""
    with open('sent_ids.json', 'w') as f:
        json.dump(sent_movie_ids, f)

def load_sent_ids():
    """Завантажує список відправлених ID з файлу."""
    if os.path.exists('sent_ids.json') and os.path.getsize('sent_ids.json') > 0:
        try:
            with open('sent_ids.json', 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Помилка при читанні JSON-файлу. Створюємо новий список.")
    return []

# --- Функції для роботи з TMDB API ---
def fetch_trending_movies():
    response = requests.get(
        f"{BASE_URL}/trending/movie/day?language=uk-UA",
        headers=headers
    )
    movies = response.json().get("results", [])
    for movie in movies:
        if movie.get("poster_path"):
            movie["poster_url"] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
        else:
            movie["poster_url"] = None
    return movies

def fetch_movies(query):
    response = requests.get(
        f"{BASE_URL}/search/movie",
        params={
            "query": query,
            "include_adult": "false",
            "language": "uk-UA",
            "page": 1
        },
        headers=headers
    )
    return response.json().get("results", [])

def fetch_movie_details(movie_id):
    response = requests.get(
        f"{BASE_URL}/movie/{movie_id}?language=uk-UA",
        headers=headers
    )
    return response.json()

def fetch_movie_cast(movie_id):
    response = requests.get(
        f"{BASE_URL}/movie/{movie_id}/credits?language=uk-UA",
        headers=headers
    )
    return response.json()

def fetch_random_movie():
    global sent_movie_ids, current_page
    
    # Завжди використовуємо тільки top_rated, переходячи по сторінках
    endpoint = "top_rated"
    
    response = requests.get(
        f"{BASE_URL}/movie/{endpoint}?language=uk-UA&page={current_page}",
        headers=headers
    )
    movies = response.json().get("results", [])
    
    if not movies:
        print(f"Досягнуто кінця списку на сторінці {current_page}. Скидаємо пам'ять і починаємо з початку.")
        sent_movie_ids = []
        current_page = 1
        return fetch_random_movie()
    
    available_movies = [movie for movie in movies if movie['id'] not in sent_movie_ids]
    
    if not available_movies:
        print(f"Всі фільми на сторінці {current_page} вже були надіслані. Перехід до наступної сторінки.")
        current_page += 1
        return fetch_random_movie()
    
    movie = random.choice(available_movies)
    sent_movie_ids.append(movie['id'])
    
    if len(sent_movie_ids) > MAX_SENT_IDS:
        sent_movie_ids.pop(0)
    
    if movie.get("poster_path"):
        movie["poster_url"] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
    
    return movie

# --- Основний код бота ---
sent_movie_ids = load_sent_ids()
if sent_movie_ids:
    print(f"Завантажено {len(sent_movie_ids)} ідентифікаторів фільмів.")
else:
    print("Файл з ідентифікаторами не знайдено, починаємо з чистого списку.")

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()
active_chats = {}

async def send_daily_movie(chat_id: int):
    try:
        current_hour = datetime.now().hour

        if 6 <= current_hour <= 11:
            greeting = "Раночку!🤗 Щоб прокинутись подивись:"
        elif 12 <= current_hour <= 16:
            greeting = "А хто це дурня клеїть?🙃 Щоб провести час з користю✊ я знайшов для тебе:"
        elif 17 <= current_hour <= 22:
            greeting = "Вже вечір! Час відпочити🍿:"
        else: # 23:00 - 5:59
            greeting = "Навіщо спати?😴 Краще подивись:"

        movie = fetch_random_movie()
        
        # Отримуємо додаткову інформацію про фільм (жанри, актори)
        details = fetch_movie_details(movie['id'])
        cast = fetch_movie_cast(movie['id'])

        # Обробка жанрів, обмеження до 5
        genres = [g['name'] for g in details.get('genres', [])][:5]
        genres_str = ", ".join(genres) if genres else "Невідомий жанр"

        # Обробка акторів, обмеження до 4
        actors = [a['name'] for a in cast.get('cast', [])][:4]
        actors_str = ", ".join(actors) if actors else "Інформація про акторів відсутня"
        
        caption = (
            f"{greeting}\n\n"
            f"**{movie['title']}** ({movie.get('release_date', '?')[:4]})\n\n"
            f"⭐ Рейтинг: **{movie.get('vote_average', '?')}/10**\n\n"
            f"🎭 Жанр: **{genres_str}**\n\n"
            f"👥 Актори: **{actors_str}**\n\n"
            f"📝 {movie.get('overview', 'Опис відсутній')}"
        )
        
        if movie.get('poster_url'):
            await bot.send_photo(
                chat_id=chat_id,
                photo=movie['poster_url'],
                caption=caption,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown"
            )
        
        print(f"Фільм '{movie['title']}' відправлено, ID збережено.")

    except Exception as e:
        print(f"Помилка відправки фільму: {e}")
    finally:
        # Зберігаємо стан в будь-якому випадку
        save_sent_ids()

@dp.message(Command("start"))
async def on_bot_added(message: types.Message):
    if message.chat.type in ('group', 'supergroup'):
        chat_id = message.chat.id
        
        if chat_id not in active_chats:
            active_chats[chat_id] = True
            
            scheduler.add_job(
                send_daily_movie,
                'interval',
                seconds=30,
                args=[chat_id]
            )
            await message.answer("🤖 Тепер я кожні 6 годин надсилатиму цікавий фільм!")
        else:
            await message.answer("🤖 Я вже працюю у цій групі!")

@dp.message(Command("trending"))
async def send_trending(message: types.Message):
    movies = fetch_trending_movies()[:10]
    
    if not movies:
        await message.answer("Не вдалося отримати трендові фільми 😕")
        return
    
    first_movie = movies[0]
    
    caption = (
        f"🎬 <b>{first_movie['title']}</b> ({first_movie.get('release_date', '?')[:4]})\n"
        f"⭐ <i>Рейтинг: {first_movie.get('vote_average', '?')}/10</i>\n"
        f"📝 {first_movie.get('overview', 'Опис відсутній')}"
    )
    
    media = [InputMediaPhoto(
        media=first_movie["poster_url"],
        caption=caption
    )]
    
    for movie in movies[1:]:
        if movie.get("poster_url"):
            media.append(InputMediaPhoto(media=movie["poster_url"]))
    
    await message.answer_media_group(media=media)

@dp.message(Command("search"))
async def search_movies(message: types.Message):
    try:
        query = message.text.split(maxsplit=1)[1]
        movies = fetch_movies(query)
        if not movies:
            await message.answer("Фільми не знайдені 😕")
            return
        
        response = "\n".join(
            f"{movie['title']} ({movie.get('release_date', '?')[:4]})" 
            for movie in movies[:3]
        )
        await message.answer(f"🔍 Результати пошуку:\n{response}")
    except IndexError:
        await message.answer("Введіть назву фільму: /search Назва")

@dp.message(Command("details"))
async def movie_details(message: types.Message):
    try:
        movie_id = message.text.split(maxsplit=1)[1]
        details = fetch_movie_details(movie_id)
        cast = fetch_movie_cast(movie_id)
        
        actors = ", ".join(actor["name"] for actor in cast.get("cast", [])[:3])
        response = (
            f"📽 {details['title']} ({details.get('release_date', '?')[:4]})\n"
            f"⭐ Рейтинг: {details.get('vote_average', '?')}/10\n"
            f"📝 {details.get('overview', 'Немає опису')[:200]}...\n"
            f"🎭 Актори: {actors}"
        )
        await message.answer(response)
    except IndexError:
        await message.answer("Введіть ID фільму: /details ID")

async def on_startup():
    scheduler.start()

async def main():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())