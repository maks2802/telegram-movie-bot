from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from api.bot import start_bot  # імпортуємо функцію для запуску бота

# Завантажуємо змінні середовища з .env
load_dotenv()

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello from Flask!'

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json  # Отримуємо запит з JSON
    print(data)
    return jsonify({'status': 'success'})

if __name__ == "__main__":
    # Запускаємо сервер Flask
    app.run(debug=True)