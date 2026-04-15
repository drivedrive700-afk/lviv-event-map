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

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
def extract_coords_from_url(url):
    try:
        # requests потрібен для розгортання коротких посилань goo.gl
        response = requests.get(url, allow_redirects=True, timeout=5)
        final_url = response.url
        # Шукаємо координати у фінальному посиланні
        match = re.search(r'([-+]?\d+\.\d+),\s*([-+]?\d+\.\d+)', final_url)
        if match:
            return float(match.group(1)), float(match.group(2))
    except Exception as e:
        print(f"Помилка розбору посилання: {e}")
    return None

# --- ВЕБ-СЕРВЕР (ДЛЯ КАРТИ) ---
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

# --- ОБРОБКА ПОВІДОМЛЕНЬ БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Бот активний!\n\nНадішли:\n1. 📎 Локацію з телефону\n2. Посилання з Google Maps\n3. Координати текстом (напр. 49.83, 24.02)\n\n/undo — видалити останню точку\n/clear — очистити все")

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if db is not None:
        await db.points.delete_many({})
        await message.answer("🧹 Карту очищено!")

@dp.message(Command("undo"))
async def cmd_undo(message: types.Message):
    if db is not None:
        # Знаходимо і видаляємо останню додану точку
        last_point = await db.points.find_one(sort=[("_id", -1)])
        if last_point:
            await db.points.delete_one({"_id": last_point["_id"]})
            await message.answer("⬅️ Останню подію видалено з карти!")
        else:
            await message.answer("Карта вже порожня.")

# 1. ПРІОРИТЕТ: Чекаємо на опис (якщо стан активовано)
@dp.message(EventForm.waiting_for_description)
async def handle_description(message: types.Message, state: FSMContext):
    # Якщо прийшла команда під час очікування опису - ігноруємо
    if not message.text or message.text.startswith('/'): return
    
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
        await message.answer("✅ Подію успішно додано на карту!")
    await state.clear()

# 2. Пряма локація (📎)
@dp.message(F.location)
async def handle_location(message: types.Message, state: FSMContext):
    await state.update_data(lat=message.location.latitude, lng=message.location.longitude)
    await state.set_state(EventForm.waiting_for_description)
    await message.answer("✅ Локацію прийнято! Тепер напиши опис події:")

# 3. Текст (координати або посилання)
@dp.message(F.text)
async def handle_text_location(message: types.Message, state: FSMContext):
    if message.text.startswith('/'): return
    
    text = message.text
    lat, lng = None, None

    # Перевірка на координати (напр. 49.835213, 23.993966)
    coords_match = re.search(r'([-+]?\d+\.\d+),\s*([-+]?\d+\.\d+)', text)
    if coords_match:
        lat, lng = float(coords_match.group(1)), float(coords_match.group(2))
    
    # Перевірка на посилання
    elif "maps" in text or "goo.gl" in text:
        await message.answer("🔍 Розшифровую посилання...")
        coords = extract_coords_from_url(text)
        if coords: lat, lng = coords

    if lat and lng:
        await state.update_data(lat=lat, lng=lng)
        # Встановлюємо стан очікування опису
        await state.set_state(EventForm.waiting_for_description)
        await message.answer(f"📍 Точку знайдено: {lat}, {lng}\nТепер напиши опис події (наприклад: 'ДТП в правій смузі'):")
    else:
        await message.answer("❌ Не вдалося розпізнати локацію. Надішли координати або посилання.")

# --- ЗАПУСК ---
async def main():
    asyncio.create_task(dp.start_polling(bot))
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
