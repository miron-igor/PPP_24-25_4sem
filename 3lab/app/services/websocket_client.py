import websockets
import asyncio
import json

async def main():
    async with websockets.connect("ws://localhost:8000/ws/123") as websocket:
        print("Connected! Waiting for messages...")
        async for message in websocket:
            data = json.loads(message)
            print("\nReceived:", json.dumps(data, indent=2))

asyncio.run(main())