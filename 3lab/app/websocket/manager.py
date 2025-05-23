from typing import Dict, Set, Any
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        print(f"WebSocket подключен для задачи {task_id}")  # Логирование

    def disconnect(self, task_id: str, websocket: WebSocket):
        self.active_connections[task_id].remove(websocket)
        print(f"WebSocket отключен для задачи {task_id}")  # Логирование

    async def send_message(self, message: dict, task_id: str):
        if task_id in self.active_connections:
            print(f"Отправка сообщения для задачи {task_id}: {message}")  # Логирование
            for connection in self.active_connections[task_id]:
                await connection.send_json(message)

ws_manager = WebSocketManager()