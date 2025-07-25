# l7rtcp_poc/app/main.py
from fastapi import FastAPI
# Импортируем роутер с обработчиками эндпоинтов.
from . import handlers

# Создаем экземпляр FastAPI-приложения.
app = FastAPI(title="L7RTCP PoC Server", version="0.1.0")

# Подключаем роутер, который будет содержать все эндпоинты нашего протокола.
app.include_router(handlers.router)

# Определяем корневой эндпоинт.
@app.get("/")
async def root():
    """
    Корневой эндпоинт.
    Возвращает простое сообщение, подтверждающее, что сервер запущен.
    """
    return {"message": "L7RTCP PoC Server is running"}