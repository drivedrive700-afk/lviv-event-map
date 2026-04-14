import os
import re
import datetime
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

# --- 1. НАЛАШТУВАННЯ ТА ТОКЕН ---
# Використовуємо твій робочий токен прямо в коді як страховку
TOKEN = "8648491410:AAEmN3o_hRZwnMOsOcqMDgKjP-mIvjV5yBs"
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = "lviv_map"

# Ініціалізація бота та сервера
bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

# Глобальне підключення до бази, щоб уникнути NameError
client = AsyncIOMotorClient(MONGO_URL) if MONGO_URL else None
db = client[DB_NAME] if client else None

# --- 2. ЛОГІКА ВЕБ-СЕРВЕРА (КАРТА) ---

# Головна сторінка — тепер вона буде відкривати index.html, а не видавати 404
@app.get("/")
async def read_index():
    return FileResponse('index.html')

# Віддача даних для карти
@app.get("/data")
async def get_data():
    if db is None:
        return {"error": "MONGO_URL не знайдено у налаштуваннях Render"}
    try:
        points = await db.points.find().to_list(1000)
        for p in points:
            p["_id"] = str(p["_id"])
        return points
    except Exception as e:
        return {"error": str(e)}

# Дозволяємо браузеру бачити твою іконку marker.png
@app.get("/marker.png")
async def get_marker():
    return FileResponse('marker.png')

# --- 3. ЛОГІКА ТЕЛЕГРАМ-БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "📍 Я готовий! Надішли мені:\n"
        "1. Свою геопозицію\n"
        "2. Вибрану точку на карті\n"
        "3. Посилання з Google Maps (натисни 'Поділитися' в картах)"
    )

# Обробка типів 1 та 2 (Геопозиція та вибір на карті)
@dp.message(F.location)
async def handle_location(message: types.Message):
    if db is None:
        await message.answer("❌ Помилка: База даних не підключена (перевір MONGO_URL)")
        return
        
    lat = message.location.latitude
    lng = message.location.longitude
    
    point = {
        "coords": [lat, lng],
        "time": datetime.datetime.now().strftime("%H:%M"),
        "type": "Точка",
        "description": "Додано через Telegram",
        "geom_type": "point",
        "color": "orange"
    }
    
    await db.points.insert_one(point)
    await message.answer(f"✅ Точку збережено! ({lat}, {lng})")

# Обробка типу 3 (Посилання Google Maps)
@dp.message(F.text)
async def handle_text(message: types.Message):
    if db is None:
        return

    # Шукаємо координати у тексті посилання через @ або q=
    match = re.search(r'([-?]\d+\.\d+),([-?]\d+\.\d+)', message.text)
    if match:
        lat, lng = float(match.group(1)), float(match.group(2))
        
        point = {
            "coords": [lat, lng],
            "time": datetime.datetime.now().strftime("%H:%M"),
            "type": "Посилання",
            "description": "Додано через Google Maps",
            "geom_type": "point",
            "color": "blue"
        }
        
        await db.points.insert_one(point)
        await message.answer(f"✅ Точку за посиланням збережено! ({lat}, {lng})")
    elif message.text.startswith("/"):
        pass # Ігноруємо команди
    else:
        await message.answer("Я не бачу координат. Надішли локацію або посилання.")

# --- 4. ЗАПУСК УСЬОГО РАЗОМ ---

async def main():
    # Запуск бота в фоновому завданні
    asyncio.create_task(dp.start_polling(bot))
    
    # Налаштування порту для Render
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
