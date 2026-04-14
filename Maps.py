import os
import re
import datetime
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
import uvicorn

# 1. ТОКЕН ТА НАЛАШТУВАННЯ
# Пріоритет: змінні оточення Render, якщо ні — прямий токен
TOKEN = os.environ.get("BOT_TOKEN") or "8648491410:AAEmN3o_hRZwnMOsOcqMDgKjP-mIvjV5yBs"
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = "lviv_map"

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

# Підключення до бази (з обробкою відсутності URL)
if MONGO_URL:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
else:
    print("ПОМИЛКА: MONGO_URL не знайдено!")

# Функція для витягування координат з посилань Google Maps
def extract_coords(text):
    # Шукаємо формат @lat,lng
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', text)
    if match:
        return float(match.group(1)), float(match.group(2))
    # Шукаємо формат q=lat,lng
    match_q = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', text)
    if match_q:
        return float(match_q.group(1)), float(match_q.group(2))
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привіт! Я готовий приймати локації:\n"
        "1. Поточна геопозиція 📍\n"
        "2. Вибрана точка на карті 🗺️\n"
        "3. Посилання Google Maps 🔗"
    )

# ОБРОБКА ЛОКАЦІЙ (1 та 2 види: поточна або вибрана)
@dp.message(F.location)
async def handle_location(message: types.Message):
    lat = message.location.latitude
    lng = message.location.longitude
    
    point = {
        "type": "Точка",
        "description": "Локація додана з Telegram",
        "time": datetime.datetime.now().strftime("%H:%M"),
        "coords": [lat, lng],
        "color": "orange",
        "geom_type": "point"
    }
    
    await db.points.insert_one(point)
    await message.answer(f"✅ Локацію прийнято!\nКоординати: `{lat}, {lng}`")

# ОБРОБКА ТЕКСТУ (3 вид: Посилання)
@dp.message(F.text)
async def handle_text(message: types.Message):
    coords = extract_coords(message.text)
    if coords:
        lat, lng = coords
        point = {
            "type": "Посилання",
            "description": "Додано через Google Maps",
            "time": datetime.datetime.now().strftime("%H:%M"),
            "coords": [lat, lng],
            "color": "blue",
            "geom_type": "point"
        }
        await db.points.insert_one(point)
        await message.answer(f"✅ Точку за посиланням додано!\nКоординати: `{lat}, {lng}`")
    else:
        await message.answer("Це не схоже на локацію або посилання Google Maps. Спробуй ще раз.")

@app.get("/data")
async def get_data():
    points = await db.points.find().to_list(1000)
    for p in points:
        p["_id"] = str(p["_id"])
    return points

async def main():
    # Запуск бота
    asyncio.create_task(dp.start_polling(bot))
    # Запуск сервера для карти
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
