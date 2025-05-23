import websockets
import asyncio
import json

async def listen():
    async with websockets.connect("ws://localhost:8000/ws/11") as websocket:
        print("Соединение установлено. Ожидание сообщений...")
        try:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                print("\nПолучено сообщение:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
        except websockets.exceptions.ConnectionClosed:
            print("Соединение закрыто.")

asyncio.run(listen())