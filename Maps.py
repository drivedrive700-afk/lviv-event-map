import os, re, datetime, asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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

# --- ВЕБ-СЕРВЕР ---

@app.get("/")
async def read_index(): 
    return FileResponse('index.html')

# Додаємо прямий шлях до картинки
@app.get("/marker.png")
async def get_marker():
    return FileResponse('marker.png')

@app.get("/data")
async def get_data():
    if db is None: return {"error": "No DB"}
    try:
        points = await db.points.find().to_list(1000)
        for p in points: p["_id"] = str(p["_id"])
        return points
    except Exception as e:
        return {"error": str(e)}

# --- КОМАНДИ БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Бот активний! Надішли локацію, і я запитаю опис.")

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if db is not None:
        await db.points.delete_many({})
        await message.answer("🧹 Карта очищена!")

@dp.message(Command("undo"))
async def cmd_undo(message: types.Message):
    if db is not None:
        last = await db.points.find_one(sort=[("_id", -1)])
        if last:
            await db.points.delete_one({"_id": last["_id"]})
            await message.answer(f"🗑 Видалено: {last.get('description', '')}")

# --- ЛОГІКА ДОДАВАННЯ ---

@dp.message(F.location)
async def handle_location(message: types.Message, state: FSMContext):
    await state.update_data(lat=message.location.latitude, lng=message.location.longitude)
    await state.set_state(EventForm.waiting_for_description)
    await message.answer("📍 Локацію отримано! Напиши опис події:")

@dp.message(EventForm.waiting_for_description)
async def handle_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if db is not None:
        await db.points.insert_one({
            "coords": [data['lat'], data['lng']],
            "time": datetime.datetime.now().strftime("%H:%M"),
            "description": message.text,
            "color": "orange",
            "geom_type": "point"
        })
        await message.answer("✅ Подію додано!")
    await state.clear()

async def main():
    asyncio.create_task(dp.start_polling(bot))
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    await uvicorn.Server(config).serve()

if __name__ == "__main__":
    asyncio.run(main())
