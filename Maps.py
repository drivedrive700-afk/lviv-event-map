import logging
import asyncio
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import uvicorn
import threading

# ================== НАЛАШТУВАННЯ ==================
API_TOKEN = "8648491410:AAEmN3o_hRZwnMOsOcqMDgKjP-mIvjV5yBs"
ADMINS = [5242383397, 131787513, 393692670]
TIMEZONE = "Europe/Kyiv"
DATA_FILE = "points.json"

app = FastAPI()
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

class MapState(StatesGroup):
    choosing_type = State()    
    waiting_location = State() 
    waiting_second_point = State() 
    waiting_comment = State()

# Допоміжна функція запису (зберігає дані назавжди у файл)
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
    match = re.search(r'([-+]?\d+\.\d+)[,\s]+([-+]?\d+\.\d+)', text)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None

# ================== ЛОГІКА БОТА ==================

@dp.message(Command("start"), F.from_user.id.in_(ADMINS))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = [
        [types.KeyboardButton(text="📍 Точка")],
        [types.KeyboardButton(text="📏 Лінія")]
    ]
    await message.answer("Оберіть інструмент:", 
                         reply_markup=types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(MapState.choosing_type)

@dp.message(MapState.choosing_type)
async def process_type(message: types.Message, state: FSMContext):
    # Виправлена логіка перевірки
    choice = message.text.strip()
    if choice == "📍 Точка":
        await state.update_data(type="point")
        await message.answer("Надішліть локацію точки (шпилька або посилання):")
        await state.set_state(MapState.waiting_location)
    elif choice == "📏 Лінія":
        await state.update_data(type="line")
        await message.answer("Надішліть ПЕРШУ точку ділянки:")
        await state.set_state(MapState.waiting_location)
    else:
        await message.answer("Будь ласка, використовуйте кнопки.")

@dp.message(MapState.waiting_location, F.location | F.text)
async def handle_first_point(message: types.Message, state: FSMContext):
    lat, lon = None, None
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
    elif message.text:
        coords = await parse_coords(message.text)
        if coords: lat, lon = coords

    if lat is None:
        return await message.answer("Координати не знайдено. Спробуйте ще раз.")

    data = await state.get_data()
    if data['type'] == "point":
        await state.update_data(coords=[lat, lon])
        await message.answer("Напишіть опис події:")
        await state.set_state(MapState.waiting_comment)
    else:
        await state.update_data(point1=[lat, lon])
        await message.answer("Тепер надішліть ДРУГУ точку:")
        await state.set_state(MapState.waiting_second_point)

@dp.message(MapState.waiting_second_point, F.location | F.text)
async def handle_second_point(message: types.Message, state: FSMContext):
    lat, lon = None, None
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
    elif message.text:
        coords = await parse_coords(message.text)
        if coords: lat, lon = coords

    if lat is None: return await message.answer("Надішліть локацію ще раз.")

    await state.update_data(point2=[lat, lon])
    await message.answer("Напишіть опис для цієї ділянки:")
    await state.set_state(MapState.waiting_comment)

@dp.message(MapState.waiting_comment)
async def finalize(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")
    
    entry = {
        "type": user_data['type'],
        "description": message.text,
        "time": now
    }
    
    if user_data['type'] == "point":
        entry["coords"] = user_data['coords']
        entry["color"] = "blue"
    else:
        entry["coords"] = [user_data['point1'], user_data['point2']]
        entry["color"] = "red"
    
    save_point(entry)
    await message.answer(f"✅ Додано! Мапа оновиться автоматично.")
    await state.clear()

# ================== СЕРВЕР ==================

@app.get("/", response_class=HTMLResponse)
async def get_map():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/data")
async def get_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return []

async def run_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск сервера в окремому потоці
    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")

    threading.Thread(target=run_server, daemon=True).start()
    print("🚀 Бот і сервер запущені!")
    asyncio.run(run_bot())
