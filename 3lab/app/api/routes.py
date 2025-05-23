# app/api/routes.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.schemas.task import TaskStatus
from app.db.database import database, task_table
from app.celery.celery import app as celery_app  # Импорт экземпляра Celery
import tempfile
import logging
from app.services.bruteforce import get_task_status

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/brut_hash", response_model=TaskStatus)
async def brut_hash(
    charset: str = Form(default="abcdefghijklmnopqrstuvwxyz0123456789"),
    max_length: int = Form(default=5, le=8),
    rar_file: UploadFile = File(...)
):
    logger.info("brut_hash endpoint was called")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".rar") as tmp:
            content = await rar_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        query = task_table.insert().values(
            file_path=tmp_path,
            charset=charset,
            max_length=max_length,
            status="running",
            progress=0,
            result=None
        )
        task_id = await database.execute(query)

        # Запуск задачи через Celery
        celery_app.send_task(
            'app.services.bruteforce.bruteforce_rar_task',
            args=[tmp_path, charset, max_length, task_id]
        )

        return {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "result": None
        }
    except Exception as e:
        logger.error(f"Error in brut_hash endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Остальной код остается без изменений
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


from fastapi import WebSocket
from app.websocket.manager import ws_manager

@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await ws_manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        ws_manager.disconnect(task_id, websocket)