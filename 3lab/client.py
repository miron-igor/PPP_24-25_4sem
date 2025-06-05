# client.py
import websockets
import asyncio
import json
import aiohttp
import os

TEST_RAR_FILE_PATH = "test.rar"

async def create_new_task():
    if not os.path.exists(TEST_RAR_FILE_PATH):
        print(f"Ошибка: Файл {TEST_RAR_FILE_PATH} не найден. Пожалуйста, создайте его или укажите правильный путь.")
        return None

    async with aiohttp.ClientSession() as session:
        form_data = aiohttp.FormData()
        form_data.add_field('charset', "abc123") 
        form_data.add_field('max_length', "4")
        form_data.add_field('rar_file',
                            open(TEST_RAR_FILE_PATH, "rb"),
                            filename=os.path.basename(TEST_RAR_FILE_PATH),
                            content_type='application/x-rar-compressed') 

        async with session.post(
            "http://localhost:8000/brut_hash",
            data=form_data
        ) as response:
            if response.status == 200:
                data = await response.json()
                print(f"Новая задача создана: {data}")
                return data["task_id"]
            else:
                error_text = await response.text()
                print(f"Ошибка создания задачи: {response.status} - {error_text}")
                return None

async def handle_task(task_id):
    uri = f"ws://localhost:8000/ws/{task_id}"
    print(f"Подключение к WebSocket для задачи {task_id} по адресу {uri}...")
    try:
        async with websockets.connect(uri) as ws:
            print(f"WebSocket соединение для задачи {task_id} установлено.")
            
            async def receiver():
                try:
                    while True:
                        msg = await ws.recv()
                        print(f"\nСообщение по задаче {task_id}:")
                        try:
                            data = json.loads(msg)
                            print(json.dumps(data, indent=2, ensure_ascii=False))
                            if data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                                print(f"Задача {task_id} завершена/отменена. Закрытие receiver.")
                                break 
                        except json.JSONDecodeError:
                            print(f"Получено не JSON сообщение: {msg}")
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"WebSocket соединение для задачи {task_id} закрыто (receiver): {e.reason} (код: {e.code})")
                except Exception as e:
                    print(f"Ошибка в receiver для задачи {task_id}: {e}")

            async def sender():
                # Даем receiver-у немного времени на подключение и получение первого сообщения, если есть
                await asyncio.sleep(0.5) 
                try:
                    while True:
                        # Проверяем, активно ли еще соединение WebSocket
                        if ws.closed:
                            print(f"WebSocket соединение для задачи {task_id} закрыто. Sender завершает работу.")
                            break
                        
                        cmd = await asyncio.to_thread(input, f"\nКоманда для задачи {task_id} (pause/resume/cancel/status/exit_current_task): ")
                        if cmd == "exit_current_task":
                            print(f"Завершение управления задачей {task_id}...")
                            # Попытка закрыть соединение со стороны клиента, если это необходимо
                            break # Выход из цикла sender

                        if ws.closed: # Еще одна проверка перед отправкой
                            print(f"WebSocket соединение для задачи {task_id} закрыто перед отправкой. Sender завершает работу.")
                            break

                        if cmd in ["pause", "resume", "cancel"]:
                             await ws.send(json.dumps({"command": cmd, "task_id": str(task_id)}))
                             print(f"Команда '{cmd}' отправлена для задачи {task_id}")
                        elif cmd == "status":
                             print("Команда 'status' должна быть реализована через HTTP GET /get_status/{task_id}")
                        else:
                             print(f"Неизвестная команда: {cmd}. Доступные команды: pause, resume, cancel, status, exit_current_task")
                        
                        # Небольшая пауза, чтобы дать время на обработку и получение ответа, если он есть
                        await asyncio.sleep(0.1)

                except websockets.exceptions.ConnectionClosed as e:
                    print(f"WebSocket соединение для задачи {task_id} закрыто (sender): {e.reason} (код: {e.code})")
                except Exception as e:
                    print(f"Ошибка в sender для задачи {task_id}: {e}")
                finally:
                    print(f"Sender для задачи {task_id} завершает работу.")
            
            # Запускаем receiver и sender параллельно
            # Если sender завершится (например, по команде exit_current_task), receiver продолжит слушать,
            # пока задача не завершится или соединение не закроется.
            # Если receiver завершится (задача COMPLETED/FAILED), sender тоже должен завершиться.
            
            receiver_task = asyncio.create_task(receiver())
            sender_task = asyncio.create_task(sender())

            # Ожидаем завершения обеих задач.
            # Если одна завершается, другая должна быть уведомлена или также завершиться.
            done, pending = await asyncio.wait(
                [receiver_task, sender_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                print(f"Отмена ожидающей задачи {task.get_name()} для task_id {task_id}")
                task.cancel()
            
            # Ждем, пока все отмененные задачи действительно завершатся
            if pending:
                await asyncio.wait(pending)

            print(f"Управление задачей {task_id} завершено.")

    except websockets.exceptions.InvalidURI:
        print(f"Ошибка: Некорректный URI для WebSocket: {uri}")
    except ConnectionRefusedError:
        print(f"Ошибка: Не удалось подключиться к WebSocket серверу по адресу {uri}. Сервер недоступен?")
    except Exception as e:
        print(f"Произошла ошибка при подключении или обработке WebSocket для задачи {task_id}: {e}")


async def main_client_loop():
    active_tasks = {}
    while True:
        action = input("\nОсновное меню клиента. Действие (new/manage/quit): ")
        if action == "new":
            task_id = await create_new_task()
            if task_id:
                # Запускаем handle_task в фоне и сохраняем ссылку на задачу
                handler = asyncio.create_task(handle_task(task_id), name=f"HandlerTask_{task_id}")
                active_tasks[task_id] = handler
                print(f"Запущена обработка для задачи {task_id}. Используйте 'manage' для взаимодействия.")
        elif action == "manage":
            if not active_tasks:
                print("Нет активных задач для управления.")
                continue
            print("Активные задачи:")
            for tid in active_tasks.keys():
                print(f"- {tid}")
            # Управление существующими задачами здесь не реализовано через это меню,
            # так как каждая задача уже имеет свой интерактивный ввод в `handle_task`.
            # Это меню просто показывает, что задачи "активны".
            # Чтобы завершить управление конкретной задачей, используйте команду 'exit_current_task' в ее собственном prompt.
            print("Для взаимодействия с задачей, отвечайте на ее собственный prompt 'Команда для задачи X ...'")
            print("Чтобы прекратить управление задачей, введите 'exit_current_task' в ее prompt.")

        elif action == "quit":
            print("Завершение работы клиента...")
            for task_id, task_obj in list(active_tasks.items()): # list() для копии, т.к. словарь может меняться
                if not task_obj.done():
                    print(f"Отмена задачи управления для task_id {task_id}...")
                    task_obj.cancel()
            
            # Даем время на завершение отмененных задач
            if active_tasks:
                 # Собираем все еще не завершенные задачи
                pending_handlers = [t for t in active_tasks.values() if not t.done()]
                if pending_handlers:
                    await asyncio.wait(pending_handlers, timeout=5.0) # Ждем до 5 секунд

            # Проверяем, все ли задачи действительно завершились
            all_done = True
            for task_id, task_obj in active_tasks.items():
                if not task_obj.done():
                    print(f"Предупреждение: Задача управления для task_id {task_id} все еще не завершена.")
                    all_done = False
            
            if all_done:
                print("Все задачи управления завершены.")
            else:
                print("Некоторые задачи управления могли не завершиться корректно.")
            break
        else:
            print(f"Неизвестное действие: {action}. Доступные действия: new, manage, quit.")

        # Убираем завершенные задачи из active_tasks
        completed_task_ids = [tid for tid, tsk in active_tasks.items() if tsk.done()]
        for tid in completed_task_ids:
            print(f"Задача управления для {tid} завершена и удалена из активного списка.")
            del active_tasks[tid]


if __name__ == "__main__":
    print("Консольный клиент для brut_hash.")
    print("Убедитесь, что файл 'test.rar' существует в той же директории, что и client.py")
    asyncio.run(main_client_loop())