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

# ================== НАЛАШТУВАННЯ ==================
API_TOKEN = "8648491410:AAEmN3o_hRZwnMOsOcqMDgKjP-mIvjV5yBs"
ADMINS = [5242383397, 131787513, 393692670]
TIMEZONE = "Europe/Kyiv"
DATA_FILE = "points.json"

# Конфігурація типів подій та їх кольорів
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

# ================== ДОПОМІЖНІ ФУНКЦІЇ ==================

def save_point(data):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            current_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        current_data = []
    
    current_data.append(data)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(current_data, f, ensure_ascii=False, indent=4)

async def parse_coords(text):
    # Пошук координат у тексті або посиланнях (Google/Apple Maps)
    pattern = r'([-+]?\d+\.\d+)[,\s]+([-+]?\d+\.\d+)'
    match = re.search(pattern, text)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None

# ================== КЛАВІАТУРИ ==================

def get_main_kb():
    keys = list(CONFIG.keys())
    # Створюємо кнопки по 2 в ряд
    buttons = [[KeyboardButton(text=keys[i]), KeyboardButton(text=keys[i+1])] for i in range(0, len(keys)-1, 2)]
    if len(keys) % 2 != 0: buttons.append([KeyboardButton(text=keys[-1])])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_location_kb():
    kb = [
        [KeyboardButton(text="📍 Надіслати мою локацію", request_location=True)],
        [KeyboardButton(text="🗺 Інструкція: вибрати на карті")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ================== ЛОГІКА БОТА ==================

@dp.message(Command("start"), F.from_user.id.in_(ADMINS))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Оберіть тип події на дорозі:", reply_markup=get_main_kb())
    await state.set_state(MapState.choosing_type)

@dp.message(MapState.choosing_type)
async def process_type(message: types.Message, state: FSMContext):
    choice = message.text.strip()
    if choice not in CONFIG:
        return await message.answer("Будь ласка, оберіть категорію з кнопок.")
    
    await state.update_data(type_label=choice, color=CONFIG[choice])
    
    if choice == "📏 Лінія":
        await state.update_data(mode="line")
        await message.answer("Надішліть ПЕРШУ точку (локація, посилання або шпилька):", reply_markup=get_location_kb())
    else:
        await state.update_data(mode="point")
        await message.answer(f"Обрано: {choice}. Тепер надішліть локацію:", reply_markup=get_location_kb())
    
    await state.set_state(MapState.waiting_location)

@dp.message(MapState.waiting_location, F.text == "🗺 Інструкція: вибрати на карті")
async def loc_help(message: types.Message):
    await message.answer("Щоб вибрати точку вручну:\n1. Натисніть 📎 (скріпку)\n2. Оберіть 'Локація'\n3. Перетягніть маркер у потрібне місце і натисніть 'Надіслати'")

@dp.message(MapState.waiting_location, F.location | F.text)
async def handle_first_point(message: types.Message, state: FSMContext):
    lat, lon = None, None
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
    elif message.text:
        coords = await parse_coords(message.text)
        if coords: lat, lon = coords

    if lat is None:
        return await message.answer("Не вдалося розпізнати координати. Надішліть локацію або посилання ще раз.")

    data = await state.get_data()
    if data.get('mode') == "point":
        await state.update_data(coords=[lat, lon])
        await message.answer("Додайте коментар (опис):", reply_markup=types.ReplyKeyboardRemove())
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
        coords = await parse_coords(message.text)
        if coords: lat, lon = coords

    if lat is None: return await message.answer("Надішліть координати другої точки.")

    await state.update_data(point2=[lat, lon])
    await message.answer("Додайте опис ділянки:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(MapState.waiting_comment)

@dp.message(MapState.waiting_comment)
async def finalize(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")
    
    entry = {
        "type": user_data['type_label'],
        "description": message.text,
        "time": now,
        "color": user_data['color']
    }
    
    if user_data['mode'] == "point":
        entry["coords"] = user_data['coords']
        entry["geom_type"] = "point"
    else:
        entry["coords"] = [user_data['point1'], user_data['point2']]
        entry["geom_type"] = "line"
    
    save_point(entry)
    await message.answer(f"✅ Успішно додано: {user_data['type_label']}\nМапа оновиться автоматично.")
    await state.clear()

# ================== СЕРВЕР ==================

@app.get("/", response_class=HTMLResponse)
async def get_map():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Файл index.html не знайдено</h1>"

@app.get("/data")
async def get_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return []

async def run_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")

    threading.Thread(target=run_server, daemon=True).start()
    print("🚀 Бот і сервер запущені!")
    asyncio.run(run_bot())

