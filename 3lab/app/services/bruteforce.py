# app/services/bruteforce.py
from typing import Optional
from app.db.database import database, task_table
import itertools
import time
from celery import shared_task
from app.websocket.manager import ws_manager
import logging
from app.services.rar_tools import check_rar_password
from app.schemas.task import TaskStatus
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

@shared_task(bind=True, name='app.services.bruteforce.bruteforce_rar_task')
def bruteforce_rar_task(self, rar_path, charset, max_length, task_id):
    """Синхронная Celery задача для перебора паролей"""
    start_time = time.time()
    
    # Отправка начального статуса
    async_to_sync(ws_manager.send_message)({
        "status": "STARTED",
        "task_id": task_id,
        "hash_type": "rar",
        "charset_length": len(charset),
        "max_length": max_length
    }, str(task_id))

    try:
        total = sum(len(charset)**l for l in range(1, max_length + 1))
        processed = 0
        last_update = time.time()
        last_progress = 0
        password_found = None

        for length in range(1, max_length + 1):
            for attempt in itertools.product(charset, repeat=length):
                password = ''.join(attempt)
                processed += 1
                current_time = time.time()

                if current_time - last_update >= 1:
                    progress = int((processed / total) * 100)
                    if progress != last_progress:
                        # Отправка прогресса через WebSocket
                        async_to_sync(ws_manager.send_message)({
                            "status": "PROGRESS",
                            "task_id": task_id,
                            "progress": progress,
                            "current_combination": password,
                            "combinations_per_second": processed / (current_time - start_time)
                        }, str(task_id))
                        
                        # Обновление БД
                        async_to_sync(update_task_progress)(task_id, progress)
                        
                        last_progress = progress
                        last_update = current_time

                if check_rar_password(rar_path, password):
                    password_found = password
                    break

            if password_found:
                break

        elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))
        if password_found:
            complete_task.delay(task_id, password_found)
            async_to_sync(ws_manager.send_message)({
                "status": "COMPLETED",
                "task_id": task_id,
                "result": password_found,
                "elapsed_time": elapsed
            }, str(task_id))
        else:
            fail_task.delay(task_id)
            async_to_sync(ws_manager.send_message)({
                "status": "FAILED",
                "task_id": task_id,
                "error": "Password not found",
                "elapsed_time": elapsed
            }, str(task_id))

        return password_found

    except Exception as e:
        fail_task.delay(task_id)
        error_info = {
            "status": "FAILED",
            "task_id": task_id,
            "error": str(e),
            "elapsed_time": time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))
        }
        async_to_sync(ws_manager.send_message)(error_info, str(task_id))
        raise

# Хелперы для работы с БД
async def update_task_progress(task_id: int, progress: int):
    """Обновление прогресса задачи в БД"""
    query = task_table.update().where(task_table.c.id == task_id).values(
        progress=progress,
        status="running" if progress < 100 else "completed"
    )
    await database.execute(query)

@shared_task
def complete_task(task_id: int, result: str):
    async def _wrapper():
        query = task_table.update().where(task_table.c.id == task_id).values(
            status="completed",
            result=result,
            progress=100
        )
        await database.execute(query)
    async_to_sync(_wrapper)()

@shared_task
def fail_task(task_id: int):
    async def _wrapper():
        query = task_table.update().where(task_table.c.id == task_id).values(
            status="failed",
            progress=100
        )
        await database.execute(query)
    async_to_sync(_wrapper)()

    
async def get_task_status(task_id: int) -> Optional[TaskStatus]:
    """Получение статуса задачи из БД (сохранено из предыдущей версии)"""
    task = await database.fetch_one(
        task_table.select().where(task_table.c.id == task_id)
    )
    if task:
        return TaskStatus(
            task_id=task["id"],
            status=task["status"],
            progress=task["progress"],
            result=task["result"]
        )
    return None