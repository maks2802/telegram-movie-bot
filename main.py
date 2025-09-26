import asyncio
import os
import json
import random
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InputMediaPhoto

# ----------------------------
# ENV + постійне сховище (Railway Volume)
# ----------------------------
load_dotenv()

DATA_DIR = os.getenv("DATA_DIR", "/data")  # На Railway змонтуй Volume у /data
os.makedirs(DATA_DIR, exist_ok=True)
SENT_IDS_PATH = os.path.join(DATA_DIR, "sent_ids.json")

BASE_URL = "https://api.themoviedb.org/3"
TMDB_TOKEN = os.getenv("TMDB_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Таймзона
TZ_NAME = os.getenv("BOT_TZ", "Europe/Kyiv")
LOCAL_TZ = ZoneInfo(TZ_NAME)

if not TELEGRAM_TOKEN:
    print("ERROR: TELEGRAM_TOKEN не задано в змінних середовища.")
    sys.exit(1)

headers = {"Authorization": f"Bearer {TMDB_TOKEN}"} if TMDB_TOKEN else {}

# ----------------------------
# Стан (пер-чатова історія)
# ----------------------------
# Замість глобального списку — мапа: chat_id(str) -> [movie_ids]
sent_movie_ids: dict[str, list[int]] = {}
MAX_SENT_IDS = 1000
current_page = 1  # трекаємо сторінки top_rated (загальні для всієї інстанції)

def _chat_key(chat_id: int) -> str:
    # зберігаємо ключі як рядки, щоб безпроблемно писати у JSON
    return str(chat_id)

def get_ids_for_chat(chat_id: int) -> list[int]:
    key = _chat_key(chat_id)
    if key not in sent_movie_ids:
        sent_movie_ids[key] = []
    return sent_movie_ids[key]

def save_sent_ids():
    """Зберігає мапу chat_id -> [ids] у файл (у Volume)."""
    try:
        with open(SENT_IDS_PATH, "w", encoding="utf-8") as f:
            json.dump(sent_movie_ids, f)
    except Exception as e:
        print(f"Помилка збереження sent_ids: {e}")

def load_sent_ids():
    """Завантажує мапу chat_id -> [ids] з файлу. Мігрує зі старого формату (list)."""
    if os.path.exists(SENT_IDS_PATH) and os.path.getsize(SENT_IDS_PATH) > 0:
        try:
            with open(SENT_IDS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Якщо старий формат: був список -> мігруємо в окремий простір
            if isinstance(data, list):
                print("Виявлено старий формат історії (list). Виконую міграцію у map per-chat.")
                return {"__legacy__": data}
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            print("Помилка читання JSON-файлу sent_ids. Створюю новий словник.")
        except Exception as e:
            print(f"Помилка читання sent_ids: {e}")
    return {}

# ----------------------------
# TMDB helpers
# ----------------------------
def fetch_trending_movies():
    try:
        resp = requests.get(
            f"{BASE_URL}/trending/movie/day",
            params={"language": "uk-UA"},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        movies = resp.json().get("results", [])
        for m in movies:
            m["poster_url"] = f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get("poster_path") else None
        return movies
    except Exception as e:
        print(f"fetch_trending_movies error: {e}")
        return []

def fetch_movies(query: str):
    try:
        resp = requests.get(
            f"{BASE_URL}/search/movie",
            params={
                "query": query,
                "include_adult": "false",
                "language": "uk-UA",
                "page": 1,
            },
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        print(f"fetch_movies error: {e}")
        return []

def fetch_movie_details(movie_id: int | str):
    try:
        resp = requests.get(
            f"{BASE_URL}/movie/{movie_id}",
            params={"language": "uk-UA"},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"fetch_movie_details error: {e}")
        return {}

def fetch_movie_credits(movie_id: int | str):
    try:
        resp = requests.get(
            f"{BASE_URL}/movie/{movie_id}/credits",
            params={"language": "uk-UA"},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"fetch_movie_credits error: {e}")
        return {}

def extract_director(credits: dict) -> str:
    crew = credits.get("crew", []) or []
    for person in crew:
        if (person.get("job") == "Director") or (
            person.get("known_for_department") == "Directing" and person.get("job") in {"Director", "Co-Director"}
        ):
            return person.get("name") or "Невідомий режисер"
    return "Невідомий режисер"

# ----------------------------
# Логіка вибору фільму (пер-чатова історія)
# ----------------------------
def fetch_random_movie(chat_id: int):
    """Ітеруємося по /movie/top_rated сторінково. Уникнення повторів — лише в рамках цього chat_id."""
    global current_page

    endpoint = "top_rated"
    try:
        resp = requests.get(
            f"{BASE_URL}/movie/{endpoint}",
            params={"language": "uk-UA", "page": current_page},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        movies = resp.json().get("results", [])
    except Exception as e:
        print(f"fetch_random_movie error: {e}")
        movies = []

    if not movies:
        print(f"Порожня сторінка {current_page}. Починаю з 1.")
        current_page = 1
        return fetch_random_movie(chat_id)

    chat_ids = get_ids_for_chat(chat_id)
    available = [m for m in movies if m.get("id") not in chat_ids]

    if not available:
        print(f"Усі фільми сторінки {current_page} вже були в чаті {chat_id}. Перехід до {current_page + 1}.")
        current_page += 1
        return fetch_random_movie(chat_id)

    movie = random.choice(available)
    chat_ids.append(movie["id"])
    if len(chat_ids) > MAX_SENT_IDS:
        chat_ids.pop(0)

    if movie.get("poster_path"):
        movie["poster_url"] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

    # Зберігаємо оновлення саме для цього чату
    sent_movie_ids[_chat_key(chat_id)] = chat_ids
    return movie

# ----------------------------
# Bot
# ----------------------------
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=LOCAL_TZ)
active_chats: dict[int, bool] = {}

async def send_daily_movie(chat_id: int):
    try:
        current_hour = datetime.now(LOCAL_TZ).hour
        if 6 <= current_hour <= 11:
            greeting = "Раночку!🤗 Щоб прокинутись подивись:"
        elif 12 <= current_hour <= 16:
            greeting = "А хто це дурня клеїть?🙃 Щоб провести час з користю✊ я знайшов для тебе:"
        elif 17 <= current_hour <= 22:
            greeting = "Вже вечір! Час відпочити🍿:"
        else:  # 23:00 - 5:59
            greeting = "Навіщо спати?😴 Краще подивись:"

        movie = fetch_random_movie(chat_id)
        if not movie:
            await bot.send_message(chat_id=chat_id, text="Схоже, TMDB недоступний. Спробую пізніше.")
            return

        details = fetch_movie_details(movie["id"])
        credits = fetch_movie_credits(movie["id"])

        genres = [g["name"] for g in details.get("genres", [])][:5]
        genres_str = ", ".join(genres) if genres else "Невідомий жанр"

        director = extract_director(credits)
        actors = [a["name"] for a in (credits.get("cast") or [])][:4]
        actors_str = ", ".join(actors) if actors else "Інформація про акторів відсутня"

        runtime_min = details.get("runtime")
        if runtime_min and isinstance(runtime_min, int):
            hours = runtime_min // 60
            minutes = runtime_min % 60
            runtime_str = f"{hours} год. {minutes} хв." if hours > 0 else f"{minutes} хв."
        else:
            runtime_str = "Невідомо"
        
        caption = (
            f"{greeting}\n\n"
            f"**{movie.get('title', 'Без назви')}** ({movie.get('release_date', '?')[:4]})\n\n"
            f"⭐ Рейтинг: **{movie.get('vote_average', '?')}/10**\n"
            f"🕒 Тривалість: **{runtime_str}**\n\n"
            f"🎭 Жанр: **{genres_str}**\n\n"
            f"🎬 Режисер: **{director}**\n\n"
            f"👥 Актори: **{actors_str}**\n\n"
            f"📝 {movie.get('overview', 'Опис відсутній')}"
        )

        if movie.get("poster_url"):
            await bot.send_photo(chat_id=chat_id, photo=movie["poster_url"], caption=caption, parse_mode="Markdown")
        else:
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")

        print(f"[{chat_id}] Відправлено: '{movie.get('title')}'.")
    except Exception as e:
        print(f"[{chat_id}] Помилка відправки фільму: {e}")
    finally:
        save_sent_ids()

@dp.message(Command("start"))
async def on_bot_added(message: types.Message):
    if message.chat.type in ("group", "supergroup", "private"):
        chat_id = message.chat.id
        if chat_id not in active_chats:
            active_chats[chat_id] = True
            scheduler.add_job(send_daily_movie, "interval", minutes=1, args=[chat_id])
            await message.answer("🤖 Я активний! Кожні 6 годин надсилатиму цікавий фільм.")
        else:
            await message.answer("🤖 Я вже працюю у цьому чаті!")

@dp.message(Command("reset"))
async def reset_ids(message: types.Message):
    chat_id = message.chat.id
    sent_movie_ids[_chat_key(chat_id)] = []
    save_sent_ids()
    await message.answer("✅ Історію цього чату очищено.")

@dp.message(Command("trending"))
async def send_trending(message: types.Message):
    movies = fetch_trending_movies()[:10]
    if not movies:
        await message.answer("Не вдалося отримати трендові фільми 😕")
        return

    first = movies[0]
    caption = (
        f"🎬 <b>{first.get('title','Без назви')}</b> ({first.get('release_date','?')[:4]})\n"
        f"⭐ <i>Рейтинг: {first.get('vote_average','?')}/10</i>\n"
        f"📝 {first.get('overview','Опис відсутній')}"
    )

    media = []
    if first.get("poster_url"):
        media.append(InputMediaPhoto(media=first["poster_url"], caption=caption, parse_mode="HTML"))
    else:
        await message.answer(caption, parse_mode="HTML")

    for m in movies[1:]:
        if m.get("poster_url"):
            media.append(InputMediaPhoto(media=m["poster_url"]))

    if media:
        await message.answer_media_group(media=media)

@dp.message(Command("search"))
async def search_movies(message: types.Message):
    try:
        query = message.text.split(maxsplit=1)[1]
    except IndexError:
        await message.answer("Введіть назву фільму: /search Назва")
        return

    movies = fetch_movies(query)
    if not movies:
        await message.answer("Фільми не знайдені 😕")
        return

    response = "\n".join(f"{m.get('title','?')} ({m.get('release_date','?')[:4]})" for m in movies[:3])
    await message.answer(f"🔍 Результати пошуку:\n{response}")

@dp.message(Command("details"))
async def movie_details_cmd(message: types.Message):
    try:
        movie_id = message.text.split(maxsplit=1)[1]
    except IndexError:
        await message.answer("Введіть ID фільму: /details ID")
        return

    details = fetch_movie_details(movie_id)
    credits = fetch_movie_credits(movie_id)
    if not details:
        await message.answer("Не вдалося отримати інформацію про фільм.")
        return

    director = extract_director(credits)
    actors = ", ".join(a.get("name", "?") for a in (credits.get("cast") or [])[:3])

    response = (
        f"📽 {details.get('title','?')} ({details.get('release_date','?')[:4]})\n"
        f"⭐ Рейтинг: {details.get('vote_average','?')}/10\n"
        f"🎬 Режисер: {director}\n"
        f"📝 {details.get('overview','Немає опису')[:200]}...\n"
        f"🎭 Актори: {actors or '—'}"
    )
    await message.answer(response)

# ----------------------------
# Запуск / Завершення
# ----------------------------
async def on_startup():
    scheduler.start()
    global sent_movie_ids
    sent_movie_ids = load_sent_ids()
    # Якщо є міграційний __legacy__, просто збережемо його як «глобальну» історію для сумісності
    if isinstance(sent_movie_ids, dict) and "__legacy__" in sent_movie_ids:
        print(f"Міграція завершена. Старих ID: {len(sent_movie_ids['__legacy__'])}. Використовуються лише пер-чатові списки надалі.")
    print(f"Історій чатів завантажено: {len(sent_movie_ids)}")

async def on_shutdown():
    try:
        save_sent_ids()
        await bot.session.close()
    except Exception as e:
        print(f"on_shutdown error: {e}")

async def main():
    await on_startup()
    try:
        # Long polling — домен/порт не потрібні
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Завершення за запитом користувача (KeyboardInterrupt).")