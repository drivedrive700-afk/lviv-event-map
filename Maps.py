import os, re, datetime, asyncio
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

# Правильна ініціалізація бази
client = AsyncIOMotorClient(MONGO_URL) if MONGO_URL else None
db = client["lviv_map"] if client else None

class EventForm(StatesGroup):
    waiting_for_description = State()

# --- ВЕБ-СЕРВЕР ---
@app.get("/")
async def read_index(): return FileResponse('index.html')

@app.get("/data")
async def get_data():
    # Виправлено помилку NotImplementedError
    if db is None: return {"error": "No DB"}
    try:
        points = await db.points.find().to_list(1000)
        for p in points: p["_id"] = str(p["_id"])
        return points
    except Exception as e:
        return {"error": str(e)}

# --- КОМАНДИ КЕРУВАННЯ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Бот ожив! Надішли локацію (скріпка 📎 -> Локація) "
        "або координати текстом, і я запитаю опис події."
    )

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if db is not None:
        await db.points.delete_many({})
        await message.answer("🧹 Карта повністю очищена!")

@dp.message(Command("undo"))
async def cmd_undo(message: types.Message):
    if db is not None:
        last_point = await db.points.find_one(sort=[("_id", -1)])
        if last_point:
            await db.points.delete_one({"_id": last_point["_id"]})
            await message.answer(f"🗑 Видалено останню точку: {last_point.get('description', '')}")

# --- ЛОГІКА ДОДАВАННЯ ---

@dp.message(F.location)
async def handle_location(message: types.Message, state: FSMContext):
    await state.update_data(lat=message.location.latitude, lng=message.location.longitude)
    await state.set_state(EventForm.waiting_for_description)
    await message.answer("📍 Локацію отримано! Тепер напиши **опис події** (тільки текст):")

@dp.message(EventForm.waiting_for_description)
async def handle_description(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    if db is not None:
        await db.points.insert_one({
            "coords": [user_data['lat'], user_data['lng']],
            "time": datetime.datetime.now().strftime("%H:%M"),
            "description": message.text, # Тільки твій текст
            "color": "orange",
            "geom_type": "point"
        })
        await message.answer("✅ Подію додано на карту!")
    await state.clear()

async def main():
    asyncio.create_task(dp.start_polling(bot))
    port = int(os.environ.get("PORT", 8000))
    # Використовуємо стандартний запуск для Render
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    await uvicorn.Server(config).serve()

if __name__ == "__main__":
    asyncio.run(main())
