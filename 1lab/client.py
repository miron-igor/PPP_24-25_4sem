import socket
import logging
import os

# Основное назначение:
# Подключение к серверу
# Отправка команд

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(name)s - %(message)s')
logger = logging.getLogger('Client')

# При ADD отправляется запрос на сервер, который добавляет программу.
# При GET клиент получает вывод программы и сохраняет его в локальную директорию, создавая её при необходимости.
# Для GET клиент ожидает данные от сервера в цикле, пока не получит все содержимое файла.
# При EXIT цикл прерывается, и клиент завершает работу.
# Все действия клиента логируются (успешное подключение, получение данных, ошибки).
def client(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        while True:
            command = input("Enter command (ADD <program> or GET <program> or EXIT): ")
            if command.lower() == "exit":
                break
            s.send(command.encode())
            if command.startswith("GET "):
                # Ожидаем получения данных от сервера
                program_name = command.split(" ")[1]
                output_file = os.path.join("programs", program_name, f"{program_name}_output.txt")
                os.makedirs(os.path.dirname(output_file), exist_ok=True)  # Создаем директорию, если необходимо
                logger.info(f"Receiving output for program {program_name}")
                with open(output_file, 'wb') as file:
                    try:
                        while True:
                            data = s.recv(4096) # Данные принимаются частями (по 4096 байт) до закрытия соединения сервером
                            if not data:
                                break
                            file.write(data)
                            logger.debug(f"Received {len(data)} bytes")
                    except ConnectionAbortedError:
                        logger.error("Connection was aborted by the server.")
                logger.info(f"Received output for program {program_name}")
            else:
                response = s.recv(1024).decode()
                logger.info(f"Server response: {response}")

if __name__ == "__main__":
    client("localhost", 12345)
