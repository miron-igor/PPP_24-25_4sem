# app/celery/celery.py
from celery import Celery, signals
from databases import Database
from app.core.config import REDIS_URL, DATABASE_URL as CORE_DATABASE_URL
import asyncio
import logging

logger = logging.getLogger(__name__)

app = Celery(
    'tasks',
    broker=REDIS_URL,  # Используем REDIS_URL из config.py
    backend=REDIS_URL, # Используем REDIS_URL из config.py
    include=['app.services.bruteforce']
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC', 
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_db_instance = Database(CORE_DATABASE_URL) 
def get_or_create_event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
        raise

@signals.worker_process_init.connect
def init_db_connection(**kwargs):
    logger.info("Celery Worker: Initializing DB connection...")
    try:
        loop = get_or_create_event_loop()
        if not celery_db_instance.is_connected:
            loop.run_until_complete(celery_db_instance.connect()) 
            logger.info("Celery Worker: DB connection established.") 
        else:
            logger.info("Celery Worker: DB connection was already established.")
    except Exception as e:
        logger.error(f"Celery Worker: Error connecting to DB: {e}", exc_info=True)
        raise

@signals.worker_process_shutdown.connect
def close_db_connection(**kwargs):
    logger.info("Celery Worker: Closing DB connection...")
    try:
        if celery_db_instance.is_connected:
            loop = get_or_create_event_loop() 
            loop.run_until_complete(celery_db_instance.disconnect())
            logger.info("Celery Worker: DB connection closed.")
    except Exception as e:
        logger.error(f"Celery Worker: Error closing DB connection: {e}", exc_info=True)