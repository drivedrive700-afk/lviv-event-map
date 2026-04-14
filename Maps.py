import logging
import asyncio
import json
import re
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

# ================== НАЛАШТУВАННЯ ==================
API_TOKEN = "8648491410:AAEmN3o_hRZwnMOsOcqMDgKjP-mIvjV5yBs"
ADMINS = [5242383397, 131787513, 393692670]
TIMEZONE = "Europe/Kyiv"

# Твій рядок підключення до MongoDB Atlas
MONGO_URL = "mongodb+srv://drivedrive700_db_user:QsGqw07nEfdKQo99@cluster0.ephhnba.mongodb.net/?appName=Cluster0"

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client.road_map_db
collection = db.points

CONFIG = {
    "🚗 ДТП": "red",
    "🚧 Роботи": "orange",
    "🚫 Перекрито": "black",
    "⚠️ Небезпека": "purple",
    "📍 Точка": "blue",
    "📏 Лінія": "darkred"
}

app = FastAPI()
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

class MapState(StatesGroup):
    choosing_type = State()    
    waiting_location = State() 
    waiting_second_point = State() 
    waiting_comment = State()

# ================== КЛАВІАТУРИ ==================

def get_main_kb():
    keys = list(CONFIG.keys())
    buttons = [[KeyboardButton(text=keys[i]), KeyboardButton(text=keys[i+1])] for i in range(0, len(keys)-1, 2)]
    if len(keys) % 2 != 0: buttons.append([KeyboardButton(text=keys[-1])])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_location_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Надіслати мою локацію", request_location=True)],
        [KeyboardButton(text="🗺 Інструкція")]
    ], resize_keyboard=True)

# ================== ЛОГІКА БОТА ==================

@dp.message(Command("start"), F.from_user.id.in_(ADMINS))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Оберіть подію на дорозі:", reply_markup=get_main_kb())
    await state.set_state(MapState.choosing_type)

@dp.message(MapState.choosing_type)
async def process_type(message: types.Message, state: FSMContext):
    if message.text not in CONFIG:
        return await message.answer("Використовуйте кнопки меню.")
    
    await state.update_data(type_label=message.text, color=CONFIG[message.text])
    mode = "line" if message.text == "📏 Лінія" else "point"
    await state.update_data(mode=mode)
    
    msg = "Надішліть ПЕРШУ точку ділянки:" if mode == "line" else "Надішліть локацію (кнопка 📍 або шпилька):"
    await message.answer(msg, reply_markup=get_location_kb())
    await state.set_state(MapState.waiting_location)

@dp.message(MapState.waiting_location, F.location | F.text)
async def handle_first_point(message: types.Message, state: FSMContext):
    lat, lon = None, None
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
    elif message.text:
        match = re.search(r'([-+]?\d+\.\d+)[,\s]+([-+]?\d+\.\d+)', message.text)
        if match: lat, lon = float(match.group(1)), float(match.group(2))

    if lat is None: return await message.answer("Координати не розпізнано. Спробуйте ще раз.")

    data = await state.get_data()
    if data['mode'] == "point":
        await state.update_data(coords=[lat, lon])
        await message.answer("Напишіть коментар (опис):", reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(MapState.waiting_comment)
    else:
        await state.update_data(point1=[lat, lon])
        await message.answer("Тепер надішліть ДРУГУ точку ділянки:")
        await state.set_state(MapState.waiting_second_point)

@dp.message(MapState.waiting_second_point, F.location | F.text)
async def handle_second_point(message: types.Message, state: FSMContext):
    lat, lon = None, None
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
    elif message.text:
        match = re.search(r'([-+]?\d+\.\d+)[,\s]+([-+]?\d+\.\d+)', message.text)
        if match: lat, lon = float(match.group(1)), float(match.group(2))

    if lat is None: return await message.answer("Надішліть другу точку ще раз.")
    await state.update_data(point2=[lat, lon])
    await message.answer("Напишіть коментар для цієї ділянки:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(MapState.waiting_comment)

@dp.message(MapState.waiting_comment)
async def finalize(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")
    
    entry = {
        "type": user_data['type_label'],
        "description": message.text,
        "time": now,
        "color": user_data['color'],
        "geom_type": user_data['mode'],
        "coords": user_data['coords'] if user_data['mode'] == "point" else [user_data['point1'], user_data['point2']]
    }
    
    await collection.insert_one(entry)
    await message.answer(f"✅ Додано в базу! Мапа оновлюється.")
    await state.clear()

# ================== СЕРВЕР (FASTAPI) ==================

@app.get("/", response_class=HTMLResponse)
async def get_map():
    try:
        with open("index.html", "r", encoding="utf-8") as f: 
            return f.read()
    except:
        return "Файл index.html не знайдено."

@app.get("/data")
async def get_data():
    cursor = collection.find({}, {"_id": 0})
    return await cursor.to_list(length=1000)

async def run_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск сервера та бота в різних потоках
    threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8000), daemon=True).start()
    asyncio.run(run_bot())
