import os
import re
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
import uvicorn
import asyncio

# Налаштування
TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = "lviv_map"

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Допоміжна функція для витягування координат з посилань Google Maps
def extract_coords(text):
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', text)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привіт! Надішли мені локацію (поточну, вибрану на карті або посилання Google Maps), і я додам її на мапу.")

# ОБРОБКА ЛОКАЦІЇ (Поточна або вибрана на карті)
@dp.message(F.location)
async def handle_location(message: types.Message):
    lat = message.location.latitude
    lng = message.location.longitude
    
    point = {
        "type": "Подія",
        "description": "Локація додана через Telegram",
        "time": datetime.datetime.now().strftime("%H:%M"),
        "coords": [lat, lng],
        "color": "orange",
        "geom_type": "point"
    }
    
    await db.points.insert_one(point)
    await message.answer(f"✅ Точка додана! Координати: {lat}, {lng}")

# ОБРОБКА ТЕКСТУ (Посилання Google Maps)
@dp.message(F.text)
async def handle_text(message: types.Message):
    coords = extract_coords(message.text)
    if coords:
        lat, lng = coords
        point = {
            "type": "Точка за посиланням",
            "description": "Додано через Google Maps link",
            "time": datetime.datetime.now().strftime("%H:%M"),
            "coords": [lat, lng],
            "color": "blue",
            "geom_type": "point"
        }
        await db.points.insert_one(point)
        await message.answer(f"✅ Точка з посилання додана: {lat}, {lng}")
    else:
        await message.answer("Я не знайшов координат у повідомленні. Надішліть локацію або посилання Google Maps.")

# Ендпоінт для карти
@app.get("/data")
async def get_data():
    points = await db.points.find().to_list(1000)
    for p in points:
        p["_id"] = str(p["_id"])
    return points

async def main():
    # Запуск бота в фоні
    asyncio.create_task(dp.start_polling(bot))
    # Запуск веб-сервера
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
