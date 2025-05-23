# app/core/config.py
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# Добавьте настройки, если они нужны
class Settings:
    pass

settings = Settings()  # Создаем пустой объект настроек