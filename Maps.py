import os, re, datetime, asyncio, requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

# --- НАЛАШТУВАННЯ ---
TOKEN = "8648491410:AAEmN3o_hRZwnMOsOcqMDgKjP-mIvjV5yBs"
MONGO_URL = os.environ.get("MONGO_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

client = AsyncIOMotorClient(MONGO_URL) if MONGO_URL else None
db = client["lviv_map"] if client else None

class EventForm(StatesGroup):
    waiting_for_description = State()

# --- ФУНКЦІЯ ДЛЯ ПОСИЛАНЬ GOOGLE MAPS ---
def extract_coords(url):
    try:
        # Розпаковуємо коротке посилання
        response = requests.get(url, allow_redirects=True, timeout=5)
        final_url = response.url
        # Шукаємо координати у фінальному посиланні (@lat,lng)
        match = re.search(r'@([-+]?\d*\.\d+),([-+]?\d*\.\d+)', final_url)
        if match:
            return float(match.group(1)), float(match.group(2))
    except:
        pass
    return None

# --- ВЕБ-СЕРВЕР ---
@app.get("/")
async def read_index(): return FileResponse('index.html')

@app.get("/marker.png")
async def get_marker(): return FileResponse('marker.png')

@app.get("/data")
async def get_data():
    if db is None: return {"error": "No DB"}
    points = await db.points.find().to_list(1000)
    for p in points: p["_id"] = str(p["_id"])
    return points

# --- КОМАНДИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("📍 Надішли локацію (📎) або посилання з Google Maps!")

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if db is not None:
        await db.points.delete_many({})
        await message.answer("🧹 Очищено!")

# --- ОБРОБКА ЛОКАЦІЇ ТА ПОСИЛАНЬ ---

# Варіант 1: Пряма локація з телефону
@dp.message(F.location)
async def handle_location(message: types.Message, state: FSMContext):
    await state.update_data(lat=message.location.latitude, lng=message.location.longitude)
    await state.set_state(EventForm.waiting_for_description)
    await message.answer("✅ Локацію прийнято! Тепер напиши опис:")

# Варіант 2: Посилання з Google Maps (з ПК або телефону)
@dp.message(F.text.contains("maps"))
async def handle_link(message: types.Message, state: FSMContext):
    coords = extract_coords(message.text)
    if coords:
        lat, lng = coords
        await state.update_data(lat=lat, lng=lng)
        await state.set_state(EventForm.waiting_for_description)
        await message.answer(f"🧩 Точку {lat}, {lng} знайдено! Напиши опис події:")
    else:
        await message.answer("❌ Не вдалося дістати координати з посилання. Спробуй ще раз.")

@dp.message(EventForm.waiting_for_description)
async def handle_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if db is not None:
        await db.points.insert_one({
            "coords": [data['lat'], data['lng']],
            "time": datetime.datetime.now().strftime("%H:%M"),
            "title": "Подія",
            "description": message.text,
            "color": "orange",
            "geom_type": "point"
        })
        await message.answer("✅ Додано на карту!")
    await state.clear()

async def main():
    asyncio.create_task(dp.start_polling(bot))
    port = int(os.environ.get("PORT", 8000))
    await uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port)).serve()

if __name__ == "__main__":
    asyncio.run(main())
