# app/services/rar_tools.py
import rarfile
import tempfile
import os
import subprocess
from pathlib import Path

# Установка пути к unrar.exe (необходим для работы с RAR)
rarfile.UNRAR_TOOL = "unrar"  # Или полный путь к unrar.exe

def check_rar_password(rar_path: str, password: str) -> bool:
    """
    Проверка пароля RAR-архива.
    Возвращает True, если пароль верный.
    """
    try:
        with rarfile.RarFile(rar_path) as rf:
            rf.testrar(pwd=password)  # Пытаемся открыть архив с паролем
        return True
    except (rarfile.BadRarFile, rarfile.PasswordRequired):
        return False  # Пароль не подошел
    except Exception as e:
        raise ValueError(f"RAR check error: {str(e)}")
