import subprocess

def main():
    # Шаблон параметров для пользователя
    template = (
        "Please enter parameters for the server in the following format:\n"
        "--host <host> --port <port> --interval <interval> "
        "--programs_file <programs_file> --programs_dir <programs_dir> <programs>\n"
        "Example:\n"
        "--host localhost --port 12345 --interval 10 --programs_file programs.json "
        "--programs_dir programs file1.py file2.py\n"
        "Enter parameters: "
    )

    # Запрос параметров у пользователя
    user_input = input(template)

    # Формирование команды для запуска сервера
    server_command = ["python", "server.py"] + user_input.split()

    # Запуск сервера в отдельном процессе
    server_process = subprocess.Popen(server_command)

    # Запуск клиента в отдельном процессе
    client_process = subprocess.Popen(["python", "client.py"])

    try:
        # Ожидание завершения процессов сервера и клиента
        server_process.wait()
        client_process.wait()
    except KeyboardInterrupt:
        # Завершение процессов при прерывании
        server_process.terminate()
        client_process.terminate()

if __name__ == "__main__":
    main()
