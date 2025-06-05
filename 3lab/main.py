# main.py
from fastapi import FastAPI
from app.api.routes import router
from app.db.database import database
from contextlib import asynccontextmanager
import logging
from app.websocket.manager import ws_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Lifespan: Запуск приложения...")

    # Инициализация WebSocketManager (включая Redis и слушателя)
    logger.info("Lifespan: Инициализация WebSocketManager...")
    try:
        await ws_manager.initialize() # Этот метод настроит Redis и запустит _listen_redis
        logger.info("Lifespan: WebSocketManager успешно инициализирован.")
    except Exception as e:
        logger.error(f"Lifespan: Ошибка инициализации WebSocketManager: {e}", exc_info=True)

    # Подключение к основной БД
    logger.info("Lifespan: Подключение к базе данных...")
    try:
        await database.connect() # [cite: 44]
        logger.info("Lifespan: База данных успешно подключена.")
    except Exception as e:
        logger.error(f"Lifespan: Ошибка подключения к базе данных: {e}", exc_info=True)
        # raise # Если критично

    yield

    # Завершение работы
    logger.info("Lifespan: Завершение работы приложения...")

    logger.info("Lifespan: Закрытие ресурсов WebSocketManager...")
    await ws_manager.close_manager() # Используем метод для корректного закрытия
    logger.info("Lifespan: Ресурсы WebSocketManager освобождены.")

    if database.is_connected:
        logger.info("Lifespan: Отключение от базы данных...")
        await database.disconnect()
        logger.info("Lifespan: База данных отключена.") 
        

app = FastAPI(lifespan=lifespan)
app.include_router(router)

@app.get("/")
async def read_root(): # [cite: 45]
    logger.info("Root endpoint был вызван")
    return {"message": "Hello World from FastAPI Bruteforce Service"}
