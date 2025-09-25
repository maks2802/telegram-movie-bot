# import requests
# import os
# from dotenv import load_dotenv
# import random

# load_dotenv()

# BASE_URL = "https://api.themoviedb.org/3"
# TMDB_TOKEN = os.getenv("TMDB_TOKEN")
# headers = {
#     "Authorization": f"Bearer {TMDB_TOKEN}"
# }

# # Зберігання ID фільмів, які вже були відправлені
# sent_movie_ids = []
# MAX_SENT_IDS = 1000

# # Функції для завантаження та збереження ID
# def save_sent_ids():
#     with open('sent_ids.json', 'w') as f:
#         json.dump(sent_movie_ids, f)

# def load_sent_ids():
#     if os.path.exists('sent_ids.json'):
#         with open('sent_ids.json', 'r') as f:
#             return json.load(f)
#     return []

# # Функції для роботи з TMDB API
# def fetch_trending_movies():
#     response = requests.get(
#         f"{BASE_URL}/trending/movie/day?language=uk-UA",
#         headers=headers
#     )
#     movies = response.json().get("results", [])
#     for movie in movies:
#         if movie.get("poster_path"):
#             movie["poster_url"] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
#         else:
#             movie["poster_url"] = None
#     return movies

# def fetch_movies(query):
#     response = requests.get(
#         f"{BASE_URL}/search/movie",
#         params={
#             "query": query,
#             "include_adult": "false",
#             "language": "uk-UA",
#             "page": 1
#         },
#         headers=headers
#     )
#     return response.json().get("results", [])

# def fetch_movie_details(movie_id):
#     response = requests.get(
#         f"{BASE_URL}/movie/{movie_id}?language=uk-UA",
#         headers=headers
#     )
#     return response.json()

# def fetch_movie_cast(movie_id):
#     response = requests.get(
#         f"{BASE_URL}/movie/{movie_id}/credits?language=uk-UA",
#         headers=headers
#     )
#     return response.json()

# def fetch_random_movie():
#     global sent_movie_ids
    
#     response = requests.get(
#         f"{BASE_URL}/movie/top_rated?language=uk-UA&page=1",
#         headers=headers
#     )
#     movies = response.json().get("results", [])
    
#     if not movies:
#         response = requests.get(
#             f"{BASE_URL}/movie/popular?language=uk-UA&page=1",
#             headers=headers
#         )
#         movies = response.json().get("results", [])
    
#     available_movies = [movie for movie in movies if movie['id'] not in sent_movie_ids]
    
#     if not available_movies:
#         print("Всі фільми з поточної сторінки вже були надіслані. Оновлення списку...")
#         sent_movie_ids = []
#         return fetch_random_movie()
    
#     movie = random.choice(available_movies)
#     sent_movie_ids.append(movie['id'])
    
#     if len(sent_movie_ids) > MAX_SENT_IDS:
#         sent_movie_ids.pop(0)
    
#     if movie.get("poster_path"):
#         movie["poster_url"] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
    
#     return movie