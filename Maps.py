import logging
import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import uvicorn
import threading
import motor.motor_asyncio

# Логування, щоб ми бачили помилки в консолі Render
logging.basicConfig(level=logging.INFO)

API_TOKEN = "8648491410:AAEmN3o_hRZwnMOsOcqMDgKjP-mIvjV5yBs"
ADMINS = [5242383397, 131787513, 393692670]

# Твій рядок підключення до MongoDB
MONGO_URL = "mongodb+srv://drivedrive700_db_user:QsGqw07nEfdKQo99@cluster0.ephhnba.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

try:
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client.road_map_db
    collection = db.points
    logging.info("Підключення до MongoDB ініційовано")
except Exception as e:
    logging.error(f"Помилка MongoDB: {e}")

app = FastAPI()
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

@app.get("/", response_class=HTMLResponse)
async def get_map():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Карта скоро буде тут..."

@app.get("/data")
async def get_data():
    cursor = collection.find({}, {"_id": 0})
    return await cursor.to_list(length=1000)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id in ADMINS:
        await message.answer("Привіт! Бот працює. Надішли локацію, щоб додати точку.")
    else:
        await message.answer("У вас немає доступу.")

async def main():
    # Запуск бота і сервера разом
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    
    # Запускаємо сервер у фоні, а бота в основному потоці
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
