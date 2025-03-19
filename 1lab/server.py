import os
import json
import logging
import subprocess
import socket
import threading
import time
import signal
import sys
import argparse


# Основное назначение:
# Управление списком программ для выполнения
# Периодический запуск программ
# Сохранение результатов их работы
# Обработка клиентских запросов на добавление программ и получение их выводов

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(name)s - %(message)s')
logger = logging.getLogger('Server')

# Загрузка информации из файла
def load_programs(file_path):
    # Если файл по пути найден, возвращаем содержимое
    # Иначе возвращаем пустой список
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return json.load(file)
    return []

# Сохранение информации в файл
def save_programs(file_path, programs):
    with open(file_path, 'w') as file:
        json.dump(programs, file)

# Запуск программы и запись вывода
def run_program(program_name, output_dir):
    program_output_dir = os.path.join(output_dir, program_name)
    os.makedirs(program_output_dir, exist_ok=True)  # Создаем директорию для программы
    try:
        # Запускаем программу через subprocess.run,
        # перенаправляя её вывод (stdout/stderr) в файл <program>_output.txt.
        with open(os.path.join(program_output_dir, f"{program_name}_output.txt"), 'a') as output_file:
            result = subprocess.run(["python", program_name], stdout=output_file, stderr=output_file)
            # Логируем результат выполнения (успех или ошибку)
            logger.info(f"Program {program_name} exited with code {result.returncode}")
    except Exception as e:
        logger.error(f"Failed to run {program_name}: {e}")


# Обработка клиентских запросов
def handle_client(client_socket, programs, programs_dir):
    request = client_socket.recv(1024).decode()
    # ADD <program>: Проверяем существование файла программы и права на выполнение
    # Если проверка пройдена, программа добавляется в список
    if request.startswith("ADD "):
        program_name = request.split(" ")[1]
        logger.info(f"Attempting to add program: {program_name}")
        if os.path.exists(program_name) and os.access(program_name, os.X_OK):
            programs.append(program_name)
            logger.info(f"Program {program_name} added to the list")
            client_socket.send(b"Program added")
            # Сохраняем обновленный список программ
            save_programs(args.programs_file, programs)
        else:
            logger.error(f"Failed to add program {program_name}: not found or no execute permission")
            client_socket.send(b"Program not found or no execute permission")
    # GET <program>: Ищем файл с выводом программы и отправляем его клиенту
    # После отправки соединение закрывается
    elif request.startswith("GET "):
        program_name = request.split(" ")[1]
        output_file = os.path.join(programs_dir, program_name, f"{program_name}_output.txt")
        if os.path.exists(output_file):
            with open(output_file, 'rb') as file:
                client_socket.sendfile(file)
            logger.info(f"Sent output for program {program_name}")
        else:
            logger.error(f"Output for program {program_name} not found")
            client_socket.send(b"Output not found")
        client_socket.close()  # Закрываем соединение после отправки данных



# Основная функция сервера

'''Основная функция server настраивает сокет, слушает подключения и запускает два потока:
один для периодического запуска программ (run_programs), другой для обработки клиентских подключений (handle_clients).
Интервал между запусками программ задается аргументом interval.
При получении сигнала KeyboardInterrupt сервер сохраняет список программ и корректно завершает работу.'''
def server(host, port, interval, programs_file, programs_dir):
    programs = load_programs(programs_file)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(1)
    logger.info(f"Server started on {host}:{port}")

    def run_programs():
        while True:
            for program in programs:
                run_program(program, programs_dir)
            time.sleep(interval)

    def handle_clients():
        while True:
            client_socket, addr = server_socket.accept()
            logger.info(f"Connected by {addr}")
            client_handler = threading.Thread(target=handle_client, args=(client_socket, programs, programs_dir))
            client_handler.start()

    try:
        program_thread = threading.Thread(target=run_programs)
        client_thread = threading.Thread(target=handle_clients)
        program_thread.start()
        client_thread.start()
        program_thread.join()
        client_thread.join()
    except KeyboardInterrupt:
        logger.info("Shutting down server")
        save_programs(programs_file, programs)
        server_socket.close()
        sys.exit(0)

if __name__ == "__main__":
    # Можно настроить хост, порт, интервал запуска, файл с программами, директорию для выводов.
    # При запуске можно сразу указать программы для добавления (например, python server.py program1.py program2.py).
    parser = argparse.ArgumentParser(description="Server for running programs")
    parser.add_argument("--host", default="localhost", help="Host to bind")
    parser.add_argument("--port", type=int, default=12345, help="Port to bind")
    parser.add_argument("--interval", type=int, default=10, help="Interval between program runs")
    parser.add_argument("--programs_file", default="programs.json", help="File to load/save programs")
    parser.add_argument("--programs_dir", default="programs", help="Directory to store program outputs")
    parser.add_argument("programs", nargs="*", help="Programs to run")
    args = parser.parse_args()

    if args.programs:
        programs_file = args.programs_file
        programs = load_programs(programs_file)
        programs.extend(args.programs)
        save_programs(programs_file, programs)

    server(args.host, args.port, args.interval, args.programs_file, args.programs_dir)
