# app/core/config.py
import os
import logging

logger = logging.getLogger(__name__)

# --- Конфигурация базы данных SQLite (остается как есть) ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# --- Конфигурация подключения к Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379)) 
REDIS_DB = int(os.getenv("REDIS_DB", 0))         # Номер базы данных Redis

# Формируем URL для подключения к Redis
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

logger.info(f"Конфигурация Redis: URL = {REDIS_URL}")
logger.info("Убедитесь, что Redis сервер запущен и доступен по этому адресу.")

class Settings:
    APP_NAME: str = "Bruteforce API Service"

settings = Settings()