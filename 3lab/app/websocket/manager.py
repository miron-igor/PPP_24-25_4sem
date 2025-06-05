# app/websocket/manager.py
import asyncio
import json
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as redis
from app.core.config import REDIS_URL 

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.redis_client: Optional[redis.Redis] = None # Тип изменен на redis.Redis
        self.pubsub_listener_task: Optional[asyncio.Task] = None
        self.redis_url = REDIS_URL

    async def initialize(self):
        """Инициализирует подключение к Redis и запускает слушателя pub/sub."""
        if self.redis_client:
            try:
                # Проверка существующего соединения
                if await self.redis_client.ping():
                    logger.info("WebSocketManager: Redis client already initialized and connected.")
                    # Если слушатель по какой-то причине неактивен, перезапускаем
                    if self.pubsub_listener_task is None or self.pubsub_listener_task.done():
                        logger.info("WebSocketManager: PubSub listener task was not active, restarting...")
                        # Нужен экземпляр pubsub для нового слушателя
                        ps = self.redis_client.pubsub()
                        self.pubsub_listener_task = asyncio.create_task(self._listen_redis(ps), name="RedisPubSubListenerTask")
                    return
            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
                logger.warning(f"WebSocketManager: Existing Redis client ping failed: {e}. Re-initializing.")
                await self.close_redis_resources() # Закрыть старые ресурсы перед новой попыткой

        logger.info(f"WebSocketManager: Инициализация с Redis URL: {self.redis_url}...")
        try:
            # Создаем асинхронный клиент redis-py
            self.redis_client = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=False) # decode_responses=False для pub/sub данных в bytes
            await self.redis_client.ping()
            logger.info("WebSocketManager: Успешное подключение к Redis (через redis-py).")

            # Создаем объект PubSub
            ps = self.redis_client.pubsub()
            await ps.psubscribe("ws:*") # Подписываемся на каналы, начинающиеся с "ws:"
            logger.info("WebSocketManager: Подписка на Redis каналы 'ws:*'.")

            # Запускаем задачу прослушивания сообщений
            if self.pubsub_listener_task is None or self.pubsub_listener_task.done():
                self.pubsub_listener_task = asyncio.create_task(self._listen_redis(ps), name="RedisPubSubListenerTask")
                logger.info("WebSocketManager: Задача Redis PubSub listener запущена.")
            else:
                logger.info("WebSocketManager: Задача Redis PubSub listener уже была запущена.")

        except redis.exceptions.RedisError as e:
            logger.error(f"WebSocketManager: Ошибка подключения/подписки Redis (redis-py): {e}", exc_info=True)
            await self.close_redis_resources()
        except Exception as e:
            logger.error(f"WebSocketManager: Ошибка во время инициализации (redis-py): {e}", exc_info=True)
            await self.close_redis_resources()
            raise

    async def _listen_redis(self, ps: redis.client.PubSub): # Принимаем экземпляр PubSub
        """Слушает сообщения из Redis каналов и рассылает их клиентам."""
        logger.info("WebSocketManager: Redis PubSub listener (_listen_redis) начал прослушивание.")
        try:
            async for message in ps.listen():
                if message["type"] == "pmessage":
                    channel_name = message["channel"].decode('utf-8') # Канал в bytes
                    task_id_from_channel = channel_name.split(":", 1)[-1] if ":" in channel_name else None

                    if task_id_from_channel:
                        try:
                            data_str = message["data"].decode('utf-8') # Данные в bytes
                            data_payload = json.loads(data_str)

                            actual_task_id = data_payload.get('task_id')
                            message_content = data_payload.get('message')

                            if actual_task_id == task_id_from_channel and message_content:
                                logger.info(f"WebSocketManager: Получено из Redis (канал '{channel_name}') для задачи '{actual_task_id}': статус {message_content.get('status')}")
                                await self.broadcast_to_task(actual_task_id, message_content)
                            else:
                                logger.warning(f"WebSocketManager: Несоответствие task_id или некорректные данные из Redis. Канал: {task_id_from_channel}, Тело: {actual_task_id}.")
                        except json.JSONDecodeError:
                            logger.error(f"WebSocketManager: Не удалось декодировать JSON из Redis (канал {channel_name}): {message['data']}")
                        except Exception as e:
                            logger.error(f"WebSocketManager: Ошибка обработки сообщения из Redis (канал {channel_name}): {e}", exc_info=True)
            logger.info("WebSocketManager: Цикл прослушивания Redis (_listen_redis) завершен.")
        except asyncio.CancelledError:
            logger.info("WebSocketManager: Задача Redis PubSub listener (_listen_redis) отменена.")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"WebSocketManager: Ошибка соединения Redis в listener (_listen_redis): {e}. Listener будет остановлен.")
            # Можно добавить логику переподключения здесь, если необходимо
            # Например, вызвать self.initialize() через некоторое время.
        except Exception as e:
            logger.error(f"WebSocketManager: Непредвиденная ошибка в Redis listener (_listen_redis): {e}", exc_info=True)
        finally:
            logger.info("WebSocketManager: Redis PubSub listener (_listen_redis) завершает работу.")
            # Отписка от каналов при завершении слушателя
            if ps:
                try:
                    await ps.punsubscribe("ws:*")
                    await ps.close() # Закрываем сам объект PubSub
                    logger.info("WebSocketManager: Отписка от каналов Redis и закрытие PubSub выполнены.")
                except Exception as e_unsub:
                    logger.error(f"WebSocketManager: Ошибка во время отписки/закрытия PubSub: {e_unsub}")

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        logger.info(f"WebSocketManager: Клиент подключен к task_id '{task_id}'. Всего клиентов: {len(self.active_connections[task_id])}")

    async def disconnect(self, task_id: str, websocket: WebSocket):
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            logger.info(f"WebSocketManager: Клиент отключен от task_id '{task_id}'.")
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
                logger.info(f"WebSocketManager: Все клиенты для task_id '{task_id}' отключены.")

    async def broadcast_to_task(self, task_id: str, message_data: dict):
        if task_id in self.active_connections:
            message_json = json.dumps(message_data)
            # Итерация по копии сета для безопасности, если disconnect вызовется во время broadcast
            connections_to_send = list(self.active_connections.get(task_id, set()))

            if not connections_to_send:
                return

            results = await asyncio.gather(
                *[conn.send_text(message_json) for conn in connections_to_send],
                return_exceptions=True
            )
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_ws = connections_to_send[i]
                    logger.warning(f"WebSocketManager: Ошибка отправки сообщения клиенту (task_id '{task_id}'): {result}. Отключение.")
                    await self.disconnect(task_id, failed_ws)

    async def close_redis_resources(self):
        """Закрывает слушатель PubSub и соединение с Redis клиентом."""
        if self.pubsub_listener_task and not self.pubsub_listener_task.done():
            logger.info("WebSocketManager: Отмена задачи Redis PubSub listener...")
            self.pubsub_listener_task.cancel()
            try:
                await self.pubsub_listener_task
                logger.info("WebSocketManager: Задача Redis PubSub listener успешно отменена и завершена.")
            except asyncio.CancelledError:
                logger.info("WebSocketManager: Задача Redis PubSub listener подтвердила отмену.")
            except Exception as e:
                logger.error(f"WebSocketManager: Ошибка при ожидании отмененной задачи listener: {e}", exc_info=True)
        self.pubsub_listener_task = None

        if self.redis_client:
            logger.info("WebSocketManager: Закрытие соединения с Redis клиентом (redis-py)...")
            try:
                await self.redis_client.close() # Закрывает клиент и его пул соединений
                logger.info("WebSocketManager: Соединение с Redis клиентом (redis-py) закрыто.")
            except Exception as e:
                logger.error(f"WebSocketManager: Ошибка закрытия Redis клиента (redis-py): {e}", exc_info=True)
        self.redis_client = None
        logger.info("WebSocketManager: Ресурсы Redis освобождены.")

    # Этот метод будет вызываться из lifespan FastAPI приложения
    async def close_manager(self):
        await self.close_redis_resources()

ws_manager = WebSocketManager()