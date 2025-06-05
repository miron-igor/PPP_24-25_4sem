# app/services/rar_tools.py
import rarfile
import logging
import io

logger = logging.getLogger(__name__)

def check_rar_password(rar_path: str, password: str) -> bool:
    """
    Проверяет, подходит ли пароль к RAR архиву.
    :param rar_path: Путь к RAR файлу.
    :param password: Пароль для проверки.
    :return: True, если пароль корректен, иначе False.
    """
    rf = None
    try:
        rf = rarfile.RarFile(rar_path, 'r')
        rf.setpassword(password)
        file_list = rf.namelist()
        if file_list: # Если архив не пуст
             # Попытка прочитать небольшой фрагмент первого файла (если это не директория)
             # Это более надежная проверка, чем просто namelist() для некоторых типов архивов/ошибок
            first_file_info = rf.getinfo(file_list[0])
            if not first_file_info.isdir():
                with rf.open(first_file_info) as f:
                    f.read(1) # Прочитать 1 байт
        return True
    except rarfile.BadRarFile: # Это наиболее частое исключение при неверном пароле
        return False
    except rarfile.NoPasswort:
        logger.warning(f"Архив {rar_path} требует пароль, но он не был установлен (No Passwort exception).")
        return False
    except rarfile. PasswortErr: 
        return False
    except RuntimeError as e:
        if "bad password" in str(e).lower() or "crc check failed" in str(e).lower():
            return False
        return False # Считаем ошибку как неверный пароль, чтобы не зависнуть
    except Exception as e:
        return False # Любую другую ошибку считаем как неверный пароль
    finally:
        if rf:
            try:
                rf.close()
            except Exception:
                pass # Игнорируем ошибки при закрытии здесь