# app/services/bruteforce.py
import itertools
import asyncio
from typing import Optional
from app.db.database import database, task_table
from app.schemas.task import TaskStatus
import logging
from app.services.rar_tools import check_rar_password

logger = logging.getLogger(__name__)

async def bruteforce_rar_task(rar_path: str, charset: str, max_length: int, task_id: int):
    """
    Основная функция для перебора паролей RAR-архива.
    """
    logger.info(f"Starting RAR bruteforce for task {task_id}")
    total = sum(len(charset)**l for l in range(1, max_length + 1))
    processed = 0

    try:
        # Перебираем все возможные комбинации паролей
        for length in range(1, max_length + 1):
            for attempt in itertools.product(charset, repeat=length):
                password = ''.join(attempt)
                processed += 1

                # Обновляем прогресс каждые 100 попыток
                if processed % 100 == 0:
                    progress = int((processed / total) * 100)
                    await update_task_progress(task_id, progress)

                # Проверяем пароль на RAR-архиве
                if check_rar_password(rar_path, password):
                    logger.info(f"Password found: {password}")
                    await complete_task(task_id, password)
                    return password

        # Если пароль не найден
        await fail_task(task_id)
        return None

    except Exception as e:
        logger.error(f"Bruteforce error: {str(e)}")
        await fail_task(task_id)
        raise

async def update_task_progress(task_id: int, progress: int):
    """Обновление прогресса задачи в БД"""
    query = task_table.update().where(task_table.c.id == task_id).values(progress=progress)
    await database.execute(query)

async def complete_task(task_id: int, result: str):
    """Отметка задачи как завершенной"""
    query = task_table.update().where(task_table.c.id == task_id).values(
        status="completed",
        result=result,
        progress=100
    )
    await database.execute(query)

async def fail_task(task_id: int):
    """Отметка задачи как проваленной"""
    query = task_table.update().where(task_table.c.id == task_id).values(
        status="failed",
        progress=100
    )
    await database.execute(query)

async def get_task_status(task_id: int) -> Optional[TaskStatus]:
    """Получение статуса задачи из БД"""
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
