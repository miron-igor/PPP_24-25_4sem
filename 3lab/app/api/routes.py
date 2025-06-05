# app/api/routes.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from app.schemas.task import TaskStatus
from app.db.database import database, task_table
from app.celery.celery import app as celery_app_instance
import tempfile
import logging
from app.services.bruteforce import get_task_status
from app.websocket.manager import ws_manager
from typing import Optional
import json
from sqlalchemy.sql import select

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/brut_hash", response_model=TaskStatus)
async def brut_hash(
    charset: str = Form(default="abcdefghijklmnopqrstuvwxyz0123456789", min_length=1),
    max_length: int = Form(default=5, ge=1, le=8), # ge=1, le=8 - мин/макс длина
    rar_file: UploadFile = File(...)
):
    logger.info(f"POST /brut_hash: charset='{charset}', max_length={max_length}, file='{rar_file.filename}'")
    
    if not rar_file.filename:
        raise HTTPException(status_code=400, detail="Имя файла не может быть пустым.")
    if not rar_file.filename.endswith(".rar"):
        raise HTTPException(status_code=400, detail="Неподдерживаемый тип файла. Пожалуйста, загрузите .rar файл.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".rar") as tmp_rar_file:
            content = await rar_file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Загруженный файл пуст.")
            tmp_rar_file.write(content)
            tmp_rar_file_path = tmp_rar_file.name
        logger.info(f"Файл сохранен во временный путь: {tmp_rar_file_path}")

        insert_query = task_table.insert().values(
            file_path=tmp_rar_file_path,
            charset=charset,
            max_length=max_length,
            status="pending",
            progress=0,
            result=None,
            celery_task_id=None # Изначально None
        )
        if not database.is_connected:
            await database.connect()
        
        db_task_id = await database.execute(insert_query)
        logger.info(f"Задача создана в БД с ID: {db_task_id}")

        celery_task_async_result = celery_app_instance.send_task(
            'app.services.bruteforce.bruteforce_rar_task',
            args=[tmp_rar_file_path, charset, max_length, db_task_id]
        )
        celery_native_id = celery_task_async_result.id
        logger.info(f"Задача {db_task_id} отправлена в Celery с Celery ID: {celery_native_id}")

        update_celery_id_query = task_table.update().where(task_table.c.id == db_task_id).values(celery_task_id=celery_native_id)
        await database.execute(update_celery_id_query)
        logger.info(f"Celery ID {celery_native_id} сохранен для задачи {db_task_id} в БД.")

        return TaskStatus(
            task_id=db_task_id,
            status="pending",
            progress=0,
            result=None
        )
    except HTTPException: # Перевыброс HTTP исключений
        raise
    except Exception as e:
        logger.error(f"Ошибка в эндпоинте /brut_hash: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")


@router.get("/get_status/{task_id}", response_model=Optional[TaskStatus])
async def get_status_route(task_id: int):
    logger.info(f"GET /get_status/{task_id}")
    if task_id <= 0:
         raise HTTPException(status_code=400, detail="task_id должен быть положительным целым числом.")
    task_data = await get_task_status(task_id)
    if task_data is None:
        logger.warning(f"Задача с ID {task_id} не найдена для GET /get_status")
        raise HTTPException(
            status_code=404,
            detail=f"Task with id {task_id} not found"
        )
    return task_data


@router.websocket("/ws/{task_id_str}")
async def websocket_endpoint(websocket: WebSocket, task_id_str: str):
    try:
        # Проверка, что task_id_str можно преобразовать в int и он валиден
        db_task_id_int = int(task_id_str)
        if db_task_id_int <= 0:
            await websocket.accept() # Принять соединение, чтобы отправить ошибку
            await websocket.send_text(json.dumps({"status": "ERROR", "task_id": task_id_str, "message": "Invalid task_id format: must be a positive integer."}))
            await websocket.close(code=1008)
            return
    except ValueError:
        logger.warning(f"WebSocket: Некорректный task_id в URL: {task_id_str}")
        await websocket.accept()
        await websocket.send_text(json.dumps({"status": "ERROR", "task_id": task_id_str, "message": "Invalid task_id format: must be an integer."}))
        await websocket.close(code=1007)
        return

    await ws_manager.connect(task_id_str, websocket)
    logger.info(f"WebSocket /ws/{task_id_str}: клиент подключен.")
    try:
        while True:
            raw_data = await websocket.receive_text()
            logger.info(f"WebSocket /ws/{task_id_str}: получено сообщение от клиента: {raw_data}")
            try:
                message = json.loads(raw_data)
                command = message.get("command")
                # Клиент должен присылать task_id в сообщении, проверяем его соответствие URL
                client_msg_task_id = message.get("task_id")
                
                if client_msg_task_id != task_id_str:
                    logger.warning(f"WebSocket /ws/{task_id_str}: Mismatched task_id in command payload ('{client_msg_task_id}'). Ignoring.")
                    await websocket.send_text(json.dumps({"status": "ERROR", "task_id": task_id_str, "message": "Mismatched task_id in command payload."}))
                    continue

                if command == "pause":
                    logger.info(f"WebSocket /ws/{task_id_str}: Команда 'pause' получена. (Функционал не реализован полностью в Celery)")
                    await websocket.send_text(json.dumps({"status": "INFO", "task_id": task_id_str, "message": "Pause command received, but full pause functionality is not yet implemented in the task."}))
                elif command == "resume":
                    logger.info(f"WebSocket /ws/{task_id_str}: Команда 'resume' получена. (Функционал не реализован полностью в Celery)")
                    await websocket.send_text(json.dumps({"status": "INFO", "task_id": task_id_str, "message": "Resume command received, but full resume functionality is not yet implemented in the task."}))
                elif command == "cancel":
                    logger.info(f"WebSocket /ws/{task_id_str}: Команда 'cancel' получена.")
                    
                    query = select(task_table.c.celery_task_id, task_table.c.status).where(task_table.c.id == db_task_id_int)
                    if not database.is_connected: await database.connect() # Убедимся в подключении
                    task_record = await database.fetch_one(query)

                    if task_record and task_record["celery_task_id"]:
                        celery_id_to_cancel = task_record["celery_task_id"]
                        current_status = task_record["status"]
                        
                        if current_status not in ["completed", "failed", "cancelled", "terminated"]:
                            celery_app_instance.control.revoke(celery_id_to_cancel, terminate=True, signal='SIGTERM')
                            logger.info(f"WebSocket /ws/{task_id_str}: Отправлена команда revoke для Celery задачи {celery_id_to_cancel}.")
                            
                            # Обновляем статус в БД на 'cancelling' или 'cancelled'
                            # Celery задача сама должна обновить на финальный 'cancelled' или 'failed' если успеет
                            update_q = task_table.update().where(task_table.c.id == db_task_id_int).values(status="cancelled") # Оптимистичное обновление
                            await database.execute(update_q)
                            
                            # Отправляем подтверждение клиенту через WebSocketManager (и этому клиенту напрямую)
                            # Celery задача при корректной отмене тоже должна послать сообщение
                            cancel_confirm_msg = {"status": "CANCELLED", "task_id": task_id_str, "message": "Task cancellation requested. The task will be terminated."}
                            await ws_manager.broadcast_to_task(task_id_str, cancel_confirm_msg)
                        else:
                            logger.info(f"WebSocket /ws/{task_id_str}: Задача {db_task_id_int} уже завершена или отменена (статус: {current_status}). Команда отмены проигнорирована.")
                            await websocket.send_text(json.dumps({"status": "INFO", "task_id": task_id_str, "message": f"Task already in '{current_status}' state. Cannot cancel."}))
                    else:
                        logger.warning(f"WebSocket /ws/{task_id_str}: Не удалось найти Celery ID для задачи {db_task_id_int} для отмены, или задача не найдена.")
                        await websocket.send_text(json.dumps({"status": "ERROR", "task_id": task_id_str, "message": "Could not find Celery task ID or task to cancel."}))
                else:
                    logger.warning(f"WebSocket /ws/{task_id_str}: Неизвестная или отсутствующая команда: '{command}'")
                    await websocket.send_text(json.dumps({"status": "ERROR", "task_id": task_id_str, "message": f"Unknown or missing command: '{command}'"}))
            
            except json.JSONDecodeError:
                logger.error(f"WebSocket /ws/{task_id_str}: Invalid JSON received: {raw_data}")
                await websocket.send_text(json.dumps({"status": "ERROR", "task_id": task_id_str, "message": "Invalid JSON format."}))

    except WebSocketDisconnect:
        logger.info(f"WebSocket /ws/{task_id_str}: клиент отключился.")
    except Exception as e:
        # Не логируем exc_info для управляемых закрытий WebSocket
        if not isinstance(e, (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError)):
             logger.error(f"WebSocket /ws/{task_id_str}: непредвиденная ошибка: {e}", exc_info=True)
    finally:
        await ws_manager.disconnect(task_id_str, websocket)
        logger.info(f"WebSocket /ws/{task_id_str}: ресурсы соединения освобождены.")