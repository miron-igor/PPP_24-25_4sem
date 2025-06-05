# app/services/bruteforce.py
from typing import Optional, Dict, Any
from app.db.database import task_table
from app.celery.celery import celery_db_instance
import itertools
import time
from celery.exceptions import Ignore
import logging
from app.services.rar_tools import check_rar_password
from asgiref.sync import async_to_sync
import redis
import json
import os
import asyncio
from app.schemas.task import TaskStatus as PydanticTaskStatus
from app.db.database import database as fastapi_db_instance
from sqlalchemy.sql import select
from celery import shared_task, Task, current_task
from celery.result import AsyncResult

from app.core.config import REDIS_HOST, REDIS_PORT, REDIS_DB

logger = logging.getLogger(__name__)

def _publish_notification_to_redis(redis_client: Optional[redis.Redis], task_id_str: str, message_content: Dict[str, Any]):
    if not redis_client:
        logger.warning(f"[Task {task_id_str}] Redis client (for Celery task publishing) not available. Skipping notification: {message_content.get('status')}")
        return
    
    channel_name = f"ws:{task_id_str}"
    payload_to_redis = {
        'task_id': task_id_str,
        'message': message_content
    }
    try:
        json_payload = json.dumps(payload_to_redis)
        redis_client.publish(channel_name, json_payload)
        logger.info(f"[Task {task_id_str}] Published to Redis channel '{channel_name}': status {message_content.get('status')}")
    except redis.exceptions.RedisError as e:
        logger.error(f"[Task {task_id_str}] Redis error publishing to channel '{channel_name}': {e}") 
    except Exception as e:
        logger.error(f"[Task {task_id_str}] Unexpected error publishing to Redis (channel '{channel_name}'): {e}", exc_info=True)


async def _update_task_db_status_async(db_task_id: int, status: str, progress: Optional[int] = None, result: Optional[str] = None):
    values_to_update = {"status": status}
    if progress is not None:
        values_to_update["progress"] = progress
    if result is not None:
        values_to_update["result"] = result
    
    if not celery_db_instance.is_connected:
        logger.warning(f"[DB Update Task {db_task_id}] celery_db_instance not connected! Attempting to connect...")
        try:
            await celery_db_instance.connect()
        except Exception as e_connect:
            logger.error(f"[DB Update Task {db_task_id}] Error connecting celery_db_instance: {e_connect}")
            return

    query = task_table.update().where(task_table.c.id == db_task_id).values(**values_to_update)
    try:
        await celery_db_instance.execute(query)
        logger.info(f"[Task {db_task_id}] DB status updated: {status}, Progress: {progress}, Result: {'<set>' if result is not None else '<not_set>'}")
    except Exception as e_exec:
        logger.error(f"[DB Update Task {db_task_id}] Error executing update query: {e_exec}")


def update_task_db_status_sync(db_task_id: int, status: str, progress: Optional[int] = None, result: Optional[str] = None): 
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        async_to_sync(_update_task_db_status_async)(db_task_id, status, progress, result)
    else:
        loop.run_until_complete(_update_task_db_status_async(db_task_id, status, progress, result))


@shared_task(bind=True, name='app.services.bruteforce.bruteforce_rar_task', acks_late=True)
def bruteforce_rar_task(self: Task, rar_path: str, charset: str, max_length: int, db_task_id: int):
    task_id_str = str(db_task_id)
    celery_task_id = self.request.id
    logger.info(f"[Task {task_id_str} / Celery {celery_task_id}] Starting bruteforce: rar_path={rar_path}, charset_len={len(charset)}, max_len={max_length}")

    redis_client: Optional[redis.Redis] = None
    start_time = time.time()

    try:
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=False) 
        redis_client.ping()
        logger.info(f"[Task {task_id_str}] Sync Redis client for Celery task connected to redis (Host: {REDIS_HOST}, Port: {REDIS_PORT}).")
    except redis.exceptions.ConnectionError as e:
        logger.error(f"[Task {task_id_str}] Could not connect sync Redis client to redis(Host: {REDIS_HOST}, Port: {REDIS_PORT}): {e}. Task will run without WebSocket notifications.", exc_info=True) # [cite: 107]
        redis_client = None
    except Exception as e_conn:
        logger.error(f"[Task {task_id_str}] An unexpected error occurred setting up sync Redis client for redis: {e_conn}", exc_info=True)
        redis_client = None


    start_message = {
        "status": "STARTED", "task_id": task_id_str, "hash_type": "rar",
        "charset_length": len(charset), "max_length": max_length
    }
    _publish_notification_to_redis(redis_client, task_id_str, start_message)
    update_task_db_status_sync(db_task_id, "running", 0)

    password_found: Optional[str] = None
    processed_combinations = 0
    last_progress_update_time = start_time
    combinations_in_last_period = 0
    final_status = "failed" 
    final_result_message = "Password not found within the given constraints."

    try:
        total_combinations_approx = sum(len(charset)**l for l in range(1, max_length + 1))
        
        for length in range(1, max_length + 1):
            if password_found: break
            if AsyncResult(self.request.id).state == 'REVOKED':
                logger.info(f"[Task {task_id_str} / Celery {celery_task_id}] Task revoked. Terminating.") 
                final_status = "cancelled"
                final_result_message = "Task cancelled by user."
                raise Ignore()

            for attempt_tuple in itertools.product(charset, repeat=length):
                if AsyncResult(self.request.id).state == 'REVOKED':
                    logger.info(f"[Task {task_id_str} / Celery {celery_task_id}] Task revoked (inner loop). Terminating.")
                    final_status = "cancelled"
                    final_result_message = "Task cancelled by user."
                    raise Ignore()

                current_password = "".join(attempt_tuple)
                processed_combinations += 1
                combinations_in_last_period += 1

                if check_rar_password(rar_path, current_password):
                    password_found = current_password
                    logger.info(f"[Task {task_id_str}] Password FOUND: {password_found}")
                    final_status = "completed"
                    final_result_message = password_found
                    break
                
                current_time = time.time()
                time_since_last_update = current_time - last_progress_update_time
                if time_since_last_update >= 1.0: 
                    progress_percentage = int((processed_combinations / total_combinations_approx) * 100) if total_combinations_approx > 0 else 0 # [cite: 114]
                    progress_percentage = min(progress_percentage, 99) 
                    cps = combinations_in_last_period / time_since_last_update if time_since_last_update > 0 else 0
                    
                    progress_message = {
                        "status": "PROGRESS", "task_id": task_id_str, "progress": progress_percentage,
                        "current_combination": current_password, 
                        "combinations_per_second": round(cps, 2) 
                    }
                    _publish_notification_to_redis(redis_client, task_id_str, progress_message)
                    update_task_db_status_sync(db_task_id, "running", progress_percentage)
                    
                    combinations_in_last_period = 0 
                    last_progress_update_time = current_time
            if password_found: break
        
        if not password_found and final_status == "failed":
            logger.info(f"[Task {task_id_str}] Password not found after full bruteforce.")

    except Ignore: 
        logger.info(f"[Task {task_id_str} / Celery {celery_task_id}] Task was properly cancelled via revoke.")
    except Exception as e:
        logger.error(f"[Task {task_id_str} / Celery {celery_task_id}] Error during bruteforce: {e}", exc_info=True)
        final_status = "failed"
        final_result_message = f"Error during bruteforce: {str(e)}"
    finally:
        elapsed_time_seconds = time.time() - start_time
        elapsed_time_formatted = time.strftime("%H:%M:%S", time.gmtime(elapsed_time_seconds))

        final_progress = 100

        update_task_db_status_sync(db_task_id, final_status, final_progress, result=final_result_message)
        
        ws_status_for_notification = final_status.upper()
        ws_result_payload = None

        if final_status == "completed":
            ws_result_payload = password_found
        elif final_status == "failed" and final_result_message == "Password not found within the given constraints.":
            ws_status_for_notification = "COMPLETED"
            ws_result_payload = None 

        final_ws_message = {
            "status": ws_status_for_notification,
            "task_id": task_id_str,
            "result": ws_result_payload,
            "elapsed_time": elapsed_time_formatted
        }

        if final_status == "failed" and ws_status_for_notification == "FAILED":
            final_ws_message["error_detail"] = final_result_message
        elif final_status == "cancelled":
            final_ws_message["message"] = final_result_message


        _publish_notification_to_redis(redis_client, task_id_str, final_ws_message)
        logger.info(f"[Task {task_id_str} / Celery {celery_task_id}] Task processing finished. Status: {final_status}. Result: {final_result_message}. Time: {elapsed_time_formatted}") 

        if redis_client:
            try:
                redis_client.close()
                logger.info(f"[Task {task_id_str}] Sync Redis client for Celery task (redislite) closed.")
            except Exception as e_close:
                logger.error(f"[Task {task_id_str}] Error closing sync Redis client (redislite): {e_close}") 
        
        if rar_path and os.path.exists(rar_path):
            try:
                os.unlink(rar_path)
                logger.info(f"[Task {task_id_str}] Temporary RAR file {rar_path} deleted.")
            except OSError as e_unlink:
                logger.error(f"[Task {task_id_str}] Error deleting temporary RAR file {rar_path}: {e_unlink}") 
        
        return {"status": final_status, "result": final_result_message, "task_id": task_id_str}


async def get_task_status(db_task_id_int: int) -> Optional[PydanticTaskStatus]:
    logger.info(f"API get_task_status: Fetching status for task_id={db_task_id_int}")
    query = select(
        task_table.c.id, task_table.c.status,
        task_table.c.progress, task_table.c.result
    ).where(task_table.c.id == db_task_id_int)
    
    if not fastapi_db_instance.is_connected:
        try:
            logger.info(f"API get_task_status: FastAPI DB instance not connected. Connecting...")
            await fastapi_db_instance.connect()
        except Exception as e:
            logger.error(f"API get_task_status: Failed to connect FastAPI DB for task {db_task_id_int}: {e}")
            return None

    record = await fastapi_db_instance.fetch_one(query)
    if record:
        logger.info(f"API get_task_status: Task {db_task_id_int} found: Status={record['status']}, Progress={record['progress']}")
        return PydanticTaskStatus(
            task_id=record["id"], status=record["status"],
            progress=record["progress"], result=record["result"] 
        )
    else:
        logger.warning(f"API get_task_status: Task {db_task_id_int} not found in DB.")
        return None