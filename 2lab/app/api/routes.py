# app/api/routes.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.schemas.task import TaskStatus
from app.db.database import database, task_table
from app.services.bruteforce import bruteforce_rar_task, get_task_status
import tempfile
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/brut_hash", response_model=TaskStatus)
async def brut_hash(
    charset: str = Form(default="abcdefghijklmnopqrstuvwxyz0123456789"),
    max_length: int = Form(default=5, le=8),
    rar_file: UploadFile = File(...)
):
    logger.info("brut_hash endpoint was called")
    """
    Эндпоинт для подбора пароля RAR-архива.
    Название оставлено как /brut_hash для совместимости, но работает с RAR-файлами.

    Принимает:
    - charset: набор символов для перебора (по умолчанию: буквы и цифры)
    - max_length: максимальная длина пароля (макс. 8)
    - rar_file: загружаемый RAR-архив
    """
    try:
        # Сохраняем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".rar") as tmp:
            content = await rar_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Создаем запись в базе данных
        query = task_table.insert().values(
            file_path=tmp_path,
            charset=charset,
            max_length=max_length,
            status="running",
            progress=0,
            result=None
        )
        task_id = await database.execute(query)

        # Запускаем брутфорс в фоновом режиме
        asyncio.create_task(bruteforce_rar_task(tmp_path, charset, max_length, task_id))

        return {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "result": None
        }
    except Exception as e:
        logger.error(f"Error in brut_hash endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: int):
    logger.info(f"get_status endpoint was called with task_id: {task_id}")
    """
    Эндпоинт для проверки статуса задачи.
    Возвращает:
    - task_id: идентификатор задачи
    - status: статус (running/completed/failed)
    - progress: прогресс в процентах
    - result: найденный пароль (если есть)
    """
    task = await get_task_status(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task with id {task_id} not found"
        )
    return task
