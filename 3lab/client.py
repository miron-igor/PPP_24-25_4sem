import websockets
import asyncio
import json

async def main():
    async with websockets.connect("ws://localhost:8000/ws/123") as websocket:
        # Обработка входящих сообщений
        async for message in websocket:
            data = json.loads(message)
            print(f"Received update: {data}")

        # Отправка команд
        while True:
            command = input("Enter command (start/pause/cancel): ")
            await websocket.send(json.dumps({"command": command}))

if __name__ == "__main__":
    asyncio.run(main())