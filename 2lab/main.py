# main.py
from fastapi import FastAPI
from app.api.routes import router
from app.db.database import database, engine, metadata
from contextlib import asynccontextmanager
import logging
import uvicorn

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.include_router(router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to the database...")
    await database.connect()
    metadata.create_all(engine)
    logger.info("Database connected.")
    yield
    logger.info("Disconnecting from the database...")
    await database.disconnect()
    logger.info("Database disconnected.")

app.router.lifespan_context = lifespan

@app.get("/")
async def read_root():
    logger.info("Root endpoint was called")
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

