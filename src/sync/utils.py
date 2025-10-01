
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль с утилитарными функциями для приложения FileSync
"""

import os
import sys
import shutil
import hashlib
import platform
import subprocess
import logging
import json
import time
import datetime
import re
import uuid
import secrets
import socket
import base64
import tempfile
import threading
import multiprocessing
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union, Any, Callable
from functools import wraps
from contextlib import contextmanager

# Импортируем константы
from src.core.constants import (
    APP_NAME, APP_VERSION, APP_AUTHOR, APP_WEBSITE,
    MAX_FILENAME_LENGTH, MAX_PATH_LENGTH,
    DEFAULT_FILE_BUFFER_SIZE,
    LOG_LEVEL_DEBUG, LOG_LEVEL_INFO, LOG_LEVEL_WARNING, LOG_LEVEL_ERROR, LOG_LEVEL_CRITICAL
)

# Настройка логирования
logger = logging.getLogger(__name__)

class FileUtils:
    """Утилиты для работы с файлами и директориями"""
    
    @staticmethod
    def get_file_size(file_path: str) -> int:
        """
        Получение размера файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            int: Размер файла в байтах
        """
        try:
            return os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"Ошибка при получении размера файла {file_path}: {e}")
            return 0
    
    @staticmethod
    def get_file_hash(file_path: str, algorithm: str = "md5", buffer_size: int = DEFAULT_FILE_BUFFER_SIZE) -> str:
        """
        Получение хеша файла
        
        Args:
            file_path (str): Путь к файлу
            algorithm (str): Алгоритм хеширования (md5, sha1, sha256, sha512)
            buffer_size (int): Размер буфера для чтения файла
            
        Returns:
            str: Хеш файла
        """
        try:
            hash_func = getattr(hashlib, algorithm)()
            with open(file_path, "rb") as f:
                while chunk := f.read(buffer_size):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка при получении хеша файла {file_path}: {e}")
            return ""
    
    @staticmethod
    def get_file_modification_time(file_path: str) -> float:
        """
        Получение времени последней модификации файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            float: Время последней модификации в формате timestamp
        """
        try:
            return os.path.getmtime(file_path)
        except Exception as e:
            logger.error(f"Ошибка при получении времени модификации файла {file_path}: {e}")
            return 0.0
    
    @staticmethod
    def get_file_creation_time(file_path: str) -> float:
        """
        Получение времени создания файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            float: Время создания в формате timestamp
        """
        try:
            if platform.system() == "Windows":
                return os.path.getctime(file_path)
            else:
                stat = os.stat(file_path)
                try:
                    return stat.st_birthtime
                except AttributeError:
                    return stat.st_mtime
        except Exception as e:
            logger.error(f"Ошибка при получении времени создания файла {file_path}: {e}")
            return 0.0
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        Форматирование размера файла в читаемый вид
        
        Args:
            size_bytes (int): Размер файла в байтах
            
        Returns:
            str: Отформатированный размер файла
        """
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"
    
    @staticmethod
    def format_timestamp(timestamp: float, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """
        Форматирование timestamp в читаемый вид
        
        Args:
            timestamp (float): Время в формате timestamp
            format_str (str): Формат строки
            
        Returns:
            str: Отформатированная строка времени
        """
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime(format_str)
        except Exception as e:
            logger.error(f"Ошибка при форматировании timestamp {timestamp}: {e}")
            return ""
    
    @staticmethod
    def is_file_exists(file_path: str) -> bool:
        """
        Проверка существования файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл существует, иначе False
        """
        return os.path.isfile(file_path)
    
    @staticmethod
    def is_dir_exists(dir_path: str) -> bool:
        """
        Проверка существования директории
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            bool: True если директория существует, иначе False
        """
        return os.path.isdir(dir_path)
    
    @staticmethod
    def create_directory(dir_path: str) -> bool:
        """
        Создание директории
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            bool: True если директория успешно создана, иначе False
        """
        try:
            os.makedirs(dir_path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Ошибка при создании директории {dir_path}: {e}")
            return False
    
    @staticmethod
    def remove_file(file_path: str) -> bool:
        """
        Удаление файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл успешно удален, иначе False
        """
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {file_path}: {e}")
            return False
    
    @staticmethod
    def remove_directory(dir_path: str) -> bool:
        """
        Удаление директории
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            bool: True если директория успешно удалена, иначе False
        """
        try:
            shutil.rmtree(dir_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении директории {dir_path}: {e}")
            return False
    
    @staticmethod
    def copy_file(src_path: str, dst_path: str) -> bool:
        """
        Копирование файла
        
        Args:
            src_path (str): Путь к исходному файлу
            dst_path (str): Путь к целевому файлу
            
        Returns:
            bool: True если файл успешно скопирован, иначе False
        """
        try:
            shutil.copy2(src_path, dst_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при копировании файла {src_path} в {dst_path}: {e}")
            return False
    
    @staticmethod
    def move_file(src_path: str, dst_path: str) -> bool:
        """
        Перемещение файла
        
        Args:
            src_path (str): Путь к исходному файлу
            dst_path (str): Путь к целевому файлу
            
        Returns:
            bool: True если файл успешно перемещен, иначе False
        """
        try:
            shutil.move(src_path, dst_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при перемещении файла {src_path} в {dst_path}: {e}")
            return False
    
    @staticmethod
    def copy_directory(src_path: str, dst_path: str) -> bool:
        """
        Копирование директории
        
        Args:
            src_path (str): Путь к исходной директории
            dst_path (str): Путь к целевой директории
            
        Returns:
            bool: True если директория успешно скопирована, иначе False
        """
        try:
            shutil.copytree(src_path, dst_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при копировании директории {src_path} в {dst_path}: {e}")
            return False
    
    @staticmethod
    def move_directory(src_path: str, dst_path: str) -> bool:
        """
        Перемещение директории
        
        Args:
            src_path (str): Путь к исходной директории
            dst_path (str): Путь к целевой директории
            
        Returns:
            bool: True если директория успешно перемещена, иначе False
        """
        try:
            shutil.move(src_path, dst_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при перемещении директории {src_path} в {dst_path}: {e}")
            return False
    
    @staticmethod
    def get_directory_size(dir_path: str) -> int:
        """
        Получение размера директории
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            int: Размер директории в байтах
        """
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(dir_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    if os.path.isfile(file_path):
                        total_size += os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"Ошибка при получении размера директории {dir_path}: {e}")
        
        return total_size
    
    @staticmethod
    def get_directory_file_count(dir_path: str) -> int:
        """
        Получение количества файлов в директории
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            int: Количество файлов в директории
        """
        file_count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(dir_path):
                file_count += len(filenames)
        except Exception as e:
            logger.error(f"Ошибка при получении количества файлов в директории {dir_path}: {e}")
        
        return file_count
    
    @staticmethod
    def get_directory_dir_count(dir_path: str) -> int:
        """
        Получение количества поддиректорий в директории
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            int: Количество поддиректорий в директории
        """
        dir_count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(dir_path):
                dir_count += len(dirnames)
        except Exception as e:
            logger.error(f"Ошибка при получении количества поддиректорий в директории {dir_path}: {e}")
        
        return dir_count
    
    @staticmethod
    def get_file_list(dir_path: str, recursive: bool = False, include_dirs: bool = False) -> List[str]:
        """
        Получение списка файлов в директории
        
        Args:
            dir_path (str): Путь к директории
            recursive (bool): Рекурсивный обход поддиректорий
            include_dirs (bool): Включать директории в результат
            
        Returns:
            List[str]: Список файлов
        """
        file_list = []
        
        try:
            if recursive:
                for dirpath, dirnames, filenames in os.walk(dir_path):
                    if include_dirs:
                        for dirname in dirnames:
                            file_list.append(os.path.join(dirpath, dirname))
                    for filename in filenames:
                        file_list.append(os.path.join(dirpath, filename))
            else:
                with os.scandir(dir_path) as entries:
                    for entry in entries:
                        if include_dirs or entry.is_file():
                            file_list.append(entry.path)
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов в директории {dir_path}: {e}")
        
        return file_list
    
    @staticmethod
    def get_relative_path(file_path: str, base_path: str) -> str:
        """
        Получение относительного пути
        
        Args:
            file_path (str): Полный путь к файлу
            base_path (str): Базовый путь
            
        Returns:
            str: Относительный путь
        """
        try:
            return os.path.relpath(file_path, base_path)
        except Exception as e:
            logger.error(f"Ошибка при получении относительного пути для {file_path} относительно {base_path}: {e}")
            return file_path
    
    @staticmethod
    def get_absolute_path(file_path: str) -> str:
        """
        Получение абсолютного пути
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Абсолютный путь
        """
        try:
            return os.path.abspath(file_path)
        except Exception as e:
            logger.error(f"Ошибка при получении абсолютного пути для {file_path}: {e}")
            return file_path
    
    @staticmethod
    def get_file_extension(file_path: str) -> str:
        """
        Получение расширения файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Расширение файла
        """
        try:
            return os.path.splitext(file_path)[1].lower()
        except Exception as e:
            logger.error(f"Ошибка при получении расширения файла {file_path}: {e}")
            return ""
    
    @staticmethod
    def get_file_name(file_path: str) -> str:
        """
        Получение имени файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Имя файла
        """
        try:
            return os.path.basename(file_path)
        except Exception as e:
            logger.error(f"Ошибка при получении имени файла {file_path}: {e}")
            return ""
    
    @staticmethod
    def get_file_name_without_extension(file_path: str) -> str:
        """
        Получение имени файла без расширения
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Имя файла без расширения
        """
        try:
            return os.path.splitext(os.path.basename(file_path))[0]
        except Exception as e:
            logger.error(f"Ошибка при получении имени файла без расширения для {file_path}: {e}")
            return ""
    
    @staticmethod
    def get_parent_directory(file_path: str) -> str:
        """
        Получение родительской директории
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Путь к родительской директории
        """
        try:
            return os.path.dirname(file_path)
        except Exception as e:
            logger.error(f"Ошибка при получении родительской директории для {file_path}: {e}")
            return ""
    
    @staticmethod
    def join_paths(*paths: str) -> str:
        """
        Объединение путей
        
        Args:
            *paths (str): Пути для объединения
            
        Returns:
            str: Объединенный путь
        """
        try:
            return os.path.join(*paths)
        except Exception as e:
            logger.error(f"Ошибка при объединении путей {paths}: {e}")
            return ""
    
    @staticmethod
    def normalize_path(file_path: str) -> str:
        """
        Нормализация пути
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Нормализованный путь
        """
        try:
            return os.path.normpath(file_path)
        except Exception as e:
            logger.error(f"Ошибка при нормализации пути {file_path}: {e}")
            return file_path
    
    @staticmethod
    def is_path_valid(file_path: str) -> bool:
        """
        Проверка валидности пути
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если путь валидный, иначе False
        """
        try:
            # Проверка длины пути
            if len(file_path) > MAX_PATH_LENGTH:
                return False
            
            # Проверка длины имени файла
            file_name = FileUtils.get_file_name(file_path)
            if len(file_name) > MAX_FILENAME_LENGTH:
                return False
            
            # Проверка на недопустимые символы
            if platform.system() == "Windows":
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    if char in file_name:
                        return False
                
                # Проверка на зарезервированные имена
                reserved_names = [
                    "CON", "PRN", "AUX", "NUL",
                    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
                ]
                
                file_name_without_ext = FileUtils.get_file_name_without_extension(file_path)
                if file_name_without_ext.upper() in reserved_names:
                    return False
            else:
                # Для Unix-систем проверяем только на символ /
                if "/" in file_name:
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при проверке валидности пути {file_path}: {e}")
            return False
    
    @staticmethod
    def sanitize_file_name(file_name: str) -> str:
        """
        Очистка имени файла от недопустимых символов
        
        Args:
            file_name (str): Имя файла
            
        Returns:
            str: Очищенное имя файла
        """
        try:
            if platform.system() == "Windows":
                # Замена недопустимых символов
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    file_name = file_name.replace(char, "_")
                
                # Проверка на зарезервированные имена
                reserved_names = [
                    "CON", "PRN", "AUX", "NUL",
                    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
                ]
                
                file_name_without_ext = FileUtils.get_file_name_without_extension(file_name)
                if file_name_without_ext.upper() in reserved_names:
                    file_name = f"_{file_name}"
            else:
                # Для Unix-систем заменяем только символ /
                file_name = file_name.replace("/", "_")
            
            # Ограничение длины имени файла
            if len(file_name) > MAX_FILENAME_LENGTH:
                file_name = file_name[:MAX_FILENAME_LENGTH]
            
            return file_name
        except Exception as e:
            logger.error(f"Ошибка при очистке имени файла {file_name}: {e}")
            return file_name
    
    @staticmethod
    def create_temp_file(suffix: str = "", prefix: str = "tmp_", dir_path: str = None) -> str:
        """
        Создание временного файла
        
        Args:
            suffix (str): Суффикс имени файла
            prefix (str): Префикс имени файла
            dir_path (str): Директория для создания файла
            
        Returns:
            str: Путь к временному файлу
        """
        try:
            fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir_path)
            os.close(fd)
            return temp_path
        except Exception as e:
            logger.error(f"Ошибка при создании временного файла: {e}")
            return ""
    
    @staticmethod
    def create_temp_dir(suffix: str = "", prefix: str = "tmp_", dir_path: str = None) -> str:
        """
        Создание временной директории
        
        Args:
            suffix (str): Суффикс имени директории
            prefix (str): Префикс имени директории
            dir_path (str): Директория для создания
            
        Returns:
            str: Путь к временной директории
        """
        try:
            return tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir_path)
        except Exception as e:
            logger.error(f"Ошибка при создании временной директории: {e}")
            return ""
    
    @staticmethod
    def read_file(file_path: str, encoding: str = "utf-8") -> str:
        """
        Чтение файла
        
        Args:
            file_path (str): Путь к файлу
            encoding (str): Кодировка файла
            
        Returns:
            str: Содержимое файла
        """
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {file_path}: {e}")
            return ""
    
    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = "utf-8", mode: str = "w") -> bool:
        """
        Запись в файл
        
        Args:
            file_path (str): Путь к файлу
            content (str): Содержимое для записи
            encoding (str): Кодировка файла
            mode (str): Режим записи
            
        Returns:
            bool: True если запись успешна, иначе False
        """
        try:
            with open(file_path, mode, encoding=encoding) as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Ошибка при записи в файл {file_path}: {e}")
            return False
    
    @staticmethod
    def read_file_bytes(file_path: str) -> bytes:
        """
        Чтение файла в бинарном режиме
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bytes: Содержимое файла
        """
        try:
            with open(file_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {file_path} в бинарном режиме: {e}")
            return b""
    
    @staticmethod
    def write_file_bytes(file_path: str, content: bytes, mode: str = "wb") -> bool:
        """
        Запись в файл в бинарном режиме
        
        Args:
            file_path (str): Путь к файлу
            content (bytes): Содержимое для записи
            mode (str): Режим записи
            
        Returns:
            bool: True если запись успешна, иначе False
        """
        try:
            with open(file_path, mode) as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Ошибка при записи в файл {file_path} в бинарном режиме: {e}")
            return False
    
    @staticmethod
    def append_file(file_path: str, content: str, encoding: str = "utf-8") -> bool:
        """
        Добавление содержимого в файл
        
        Args:
            file_path (str): Путь к файлу
            content (str): Содержимое для добавления
            encoding (str): Кодировка файла
            
        Returns:
            bool: True если добавление успешно, иначе False
        """
        return FileUtils.write_file(file_path, content, encoding, "a")
    
    @staticmethod
    def append_file_bytes(file_path: str, content: bytes) -> bool:
        """
        Добавление содержимого в файл в бинарном режиме
        
        Args:
            file_path (str): Путь к файлу
            content (bytes): Содержимое для добавления
            
        Returns:
            bool: True если добавление успешно, иначе False
        """
        return FileUtils.write_file_bytes(file_path, content, "ab")
    
    @staticmethod
    def read_json_file(file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Чтение JSON файла
        
        Args:
            file_path (str): Путь к файлу
            encoding (str): Кодировка файла
            
        Returns:
            Dict[str, Any]: Содержимое JSON файла
        """
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при чтении JSON файла {file_path}: {e}")
            return {}
    
    @staticmethod
    def write_json_file(file_path: str, data: Dict[str, Any], encoding: str = "utf-8", indent: int = 4) -> bool:
        """
        Запись в JSON файл
        
        Args:
            file_path (str): Путь к файлу
            data (Dict[str, Any]): Данные для записи
            encoding (str): Кодировка файла
            indent (int): Отступ для форматирования
            
        Returns:
            bool: True если запись успешна, иначе False
        """
        try:
            with open(file_path, "w", encoding=encoding) as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Ошибка при записи в JSON файл {file_path}: {e}")
            return False
    
    @staticmethod
    def get_file_permissions(file_path: str) -> int:
        """
        Получение прав доступа к файлу
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            int: Права доступа к файлу
        """
        try:
            return os.stat(file_path).st_mode
        except Exception as e:
            logger.error(f"Ошибка при получении прав доступа к файлу {file_path}: {e}")
            return 0
    
    @staticmethod
    def set_file_permissions(file_path: str, permissions: int) -> bool:
        """
        Установка прав доступа к файлу
        
        Args:
            file_path (str): Путь к файлу
            permissions (int): Права доступа к файлу
            
        Returns:
            bool: True если установка прав успешна, иначе False
        """
        try:
            os.chmod(file_path, permissions)
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке прав доступа к файлу {file_path}: {e}")
            return False
    
    @staticmethod
    def is_file_readable(file_path: str) -> bool:
        """
        Проверка доступности файла для чтения
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл доступен для чтения, иначе False
        """
        try:
            return os.access(file_path, os.R_OK)
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности файла {file_path} для чтения: {e}")
            return False
    
    @staticmethod
    def is_file_writable(file_path: str) -> bool:
        """
        Проверка доступности файла для записи
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл доступен для записи, иначе False
        """
        try:
            return os.access(file_path, os.W_OK)
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности файла {file_path} для записи: {e}")
            return False
    
    @staticmethod
    def is_file_executable(file_path: str) -> bool:
        """
        Проверка доступности файла для выполнения
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл доступен для выполнения, иначе False
        """
        try:
            return os.access(file_path, os.X_OK)
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности файла {file_path} для выполнения: {e}")
            return False
    
    @staticmethod
    def is_dir_readable(dir_path: str) -> bool:
        """
        Проверка доступности директории для чтения
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            bool: True если директория доступна для чтения, иначе False
        """
        try:
            return os.access(dir_path, os.R_OK)
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности директории {dir_path} для чтения: {e}")
            return False
    
    @staticmethod
    def is_dir_writable(dir_path: str) -> bool:
        """
        Проверка доступности директории для записи
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            bool: True если директория доступна для записи, иначе False
        """
        try:
            return os.access(dir_path, os.W_OK)
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности директории {dir_path} для записи: {e}")
            return False
    
    @staticmethod
    def is_dir_executable(dir_path: str) -> bool:
        """
        Проверка доступности директории для выполнения
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            bool: True если директория доступна для выполнения, иначе False
        """
        try:
            return os.access(dir_path, os.X_OK)
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности директории {dir_path} для выполнения: {e}")
            return False
    
    @staticmethod
    def get_file_owner(file_path: str) -> str:
        """
        Получение владельца файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Владелец файла
        """
        try:
            if platform.system() == "Windows":
                import win32security
                sd = win32security.GetFileSecurity(file_path, win32security.OWNER_SECURITY_INFORMATION)
                owner_sid = sd.GetSecurityDescriptorOwner()
                name, domain, _ = win32security.LookupAccountSid(None, owner_sid)
                return f"{domain}\\{name}"
            else:
                import pwd
                stat = os.stat(file_path)
                return pwd.getpwuid(stat.st_uid).pw_name
        except Exception as e:
            logger.error(f"Ошибка при получении владельца файла {file_path}: {e}")
            return ""
    
    @staticmethod
    def get_file_group(file_path: str) -> str:
        """
        Получение группы файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Группа файла
        """
        try:
            if platform.system() == "Windows":
                import win32security
                sd = win32security.GetFileSecurity(file_path, win32security.GROUP_SECURITY_INFORMATION)
                group_sid = sd.GetSecurityDescriptorGroup()
                name, domain, _ = win32security.LookupAccountSid(None, group_sid)
                return f"{domain}\\{name}"
            else:
                import grp
                stat = os.stat(file_path)
                return grp.getgrgid(stat.st_gid).gr_name
        except Exception as e:
            logger.error(f"Ошибка при получении группы файла {file_path}: {e}")
            return ""
    
    @staticmethod
    def set_file_owner(file_path: str, owner: str) -> bool:
        """
        Установка владельца файла
        
        Args:
            file_path (str): Путь к файлу
            owner (str): Владелец файла
            
        Returns:
            bool: True если установка владельца успешна, иначе False
        """
        try:
            if platform.system() == "Windows":
                import win32security
                import win32con
                import win32api
                
                # Получение SID владельца
                domain, user = owner.split("\\")
                sid, _, _ = win32security.LookupAccountName(domain, user)
                
                # Установка владельца
                sd = win32security.GetFileSecurity(file_path, win32security.OWNER_SECURITY_INFORMATION)
                sd.SetSecurityDescriptorOwner(sid, False)
                win32security.SetFileSecurity(file_path, win32security.OWNER_SECURITY_INFORMATION, sd)
            else:
                import pwd
                uid = pwd.getpwnam(owner).pw_uid
                os.chown(file_path, uid, -1)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке владельца файла {file_path}: {e}")
            return False
    
    @staticmethod
    def set_file_group(file_path: str, group: str) -> bool:
        """
        Установка группы файла
        
        Args:
            file_path (str): Путь к файлу
            group (str): Группа файла
            
        Returns:
            bool: True если установка группы успешна, иначе False
        """
        try:
            if platform.system() == "Windows":
                import win32security
                import win32con
                import win32api
                
                # Получение SID группы
                domain, grp = group.split("\\")
                sid, _, _ = win32security.LookupAccountName(domain, grp)
                
                # Установка группы
                sd = win32security.GetFileSecurity(file_path, win32security.GROUP_SECURITY_INFORMATION)
                sd.SetSecurityDescriptorGroup(sid, False)
                win32security.SetFileSecurity(file_path, win32security.GROUP_SECURITY_INFORMATION, sd)
            else:
                import grp
                gid = grp.getgrnam(group).gr_gid
                os.chown(file_path, -1, gid)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке группы файла {file_path}: {e}")
            return False
    
    @staticmethod
    def get_file_attributes(file_path: str) -> Dict[str, bool]:
        """
        Получение атрибутов файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            Dict[str, bool]: Атрибуты файла
        """
        attributes = {
            "readonly": False,
            "hidden": False,
            "system": False,
            "archive": False
        }
        
        try:
            if platform.system() == "Windows":
                import win32api
                import win32con
                
                attr = win32api.GetFileAttributes(file_path)
                attributes["readonly"] = bool(attr & win32con.FILE_ATTRIBUTE_READONLY)
                attributes["hidden"] = bool(attr & win32con.FILE_ATTRIBUTE_HIDDEN)
                attributes["system"] = bool(attr & win32con.FILE_ATTRIBUTE_SYSTEM)
                attributes["archive"] = bool(attr & win32con.FILE_ATTRIBUTE_ARCHIVE)
            else:
                # Для Unix-систем используем права доступа
                stat = os.stat(file_path)
                mode = stat.st_mode
                
                # Проверка на доступность только для чтения
                if not (mode & 0o200):  # Нет прав на запись для владельца
                    attributes["readonly"] = True
                
                # Проверка на скрытый файл (начинается с точки)
                if os.path.basename(file_path).startswith("."):
                    attributes["hidden"] = True
        except Exception as e:
            logger.error(f"Ошибка при получении атрибутов файла {file_path}: {e}")
        
        return attributes
    
    @staticmethod
    def set_file_attributes(file_path: str, attributes: Dict[str, bool]) -> bool:
        """
        Установка атрибутов файла
        
        Args:
            file_path (str): Путь к файлу
            attributes (Dict[str, bool]): Атрибуты файла
            
        Returns:
            bool: True если установка атрибутов успешна, иначе False
        """
        try:
            if platform.system() == "Windows":
                import win32api
                import win32con
                
                attr = win32api.GetFileAttributes(file_path)
                
                if attributes.get("readonly", False):
                    attr |= win32con.FILE_ATTRIBUTE_READONLY
                else:
                    attr &= ~win32con.FILE_ATTRIBUTE_READONLY
                
                if attributes.get("hidden", False):
                    attr |= win32con.FILE_ATTRIBUTE_HIDDEN
                else:
                    attr &= ~win32con.FILE_ATTRIBUTE_HIDDEN
                
                if attributes.get("system", False):
                    attr |= win32con.FILE_ATTRIBUTE_SYSTEM
                else:
                    attr &= ~win32con.FILE_ATTRIBUTE_SYSTEM
                
                if attributes.get("archive", False):
                    attr |= win32con.FILE_ATTRIBUTE_ARCHIVE
                else:
                    attr &= ~win32con.FILE_ATTRIBUTE_ARCHIVE
                
                win32api.SetFileAttributes(file_path, attr)
            else:
                # Для Unix-систем используем права доступа
                stat = os.stat(file_path)
                mode = stat.st_mode
                
                # Установка прав только для чтения
                if attributes.get("readonly", False):
                    mode &= ~0o222  # Удаление прав на запись для всех
                else:
                    # Восстановление прав на запись
                    mode |= 0o200  # Права на запись для владельца
                
                os.chmod(file_path, mode)
                
                # Для скрытых файлов в Unix-системах просто переименовываем
                if attributes.get("hidden", False):
                    dir_path = FileUtils.get_parent_directory(file_path)
                    file_name = FileUtils.get_file_name(file_path)
                    
                    if not file_name.startswith("."):
                        new_file_name = f".{file_name}"
                        new_file_path = FileUtils.join_paths(dir_path, new_file_name)
                        os.rename(file_path, new_file_path)
                else:
                    dir_path = FileUtils.get_parent_directory(file_path)
                    file_name = FileUtils.get_file_name(file_path)
                    
                    if file_name.startswith("."):
                        new_file_name = file_name[1:]
                        new_file_path = FileUtils.join_paths(dir_path, new_file_name)
                        os.rename(file_path, new_file_path)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке атрибутов файла {file_path}: {e}")
            return False
    
    @staticmethod
    def hide_file(file_path: str) -> bool:
        """
        Скрытие файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл успешно скрыт, иначе False
        """
        attributes = FileUtils.get_file_attributes(file_path)
        attributes["hidden"] = True
        return FileUtils.set_file_attributes(file_path, attributes)
    
    @staticmethod
    def show_file(file_path: str) -> bool:
        """
        Отображение файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл успешно отображен, иначе False
        """
        attributes = FileUtils.get_file_attributes(file_path)
        attributes["hidden"] = False
        return FileUtils.set_file_attributes(file_path, attributes)
    
    @staticmethod
    def make_file_readonly(file_path: str) -> bool:
        """
        Установка файла только для чтения
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл успешно установлен только для чтения, иначе False
        """
        attributes = FileUtils.get_file_attributes(file_path)
        attributes["readonly"] = True
        return FileUtils.set_file_attributes(file_path, attributes)
    
    @staticmethod
    def make_file_writable(file_path: str) -> bool:
        """
        Установка файла для записи
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл успешно установлен для записи, иначе False
        """
        attributes = FileUtils.get_file_attributes(file_path)
        attributes["readonly"] = False
        return FileUtils.set_file_attributes(file_path, attributes)
    
    @staticmethod
    def get_disk_space(path: str) -> Dict[str, int]:
        """
        Получение информации о дисковом пространстве
        
        Args:
            path (str): Путь к директории
            
        Returns:
            Dict[str, int]: Информация о дисковом пространстве
        """
        try:
            if platform.system() == "Windows":
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(path), 
                    ctypes.pointer(free_bytes), 
                    ctypes.pointer(total_bytes), 
                    None
                )
                total_space = total_bytes.value
                free_space = free_bytes.value
                used_space = total_space - free_space
            else:
                stat = os.statvfs(path)
                total_space = stat.f_blocks * stat.f_frsize
                free_space = stat.f_bavail * stat.f_frsize
                used_space = total_space - free_space
            
            return {
                "total": total_space,
                "free": free_space,
                "used": used_space
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о дисковом пространстве для {path}: {e}")
            return {
                "total": 0,
                "free": 0,
                "used": 0
            }
    
    @staticmethod
    def get_mounted_drives() -> List[str]:
        """
        Получение списка смонтированных дисков
        
        Returns:
            List[str]: Список смонтированных дисков
        """
        try:
            if platform.system() == "Windows":
                import win32api
                drives = win32api.GetLogicalDriveStrings()
                drives = drives.split("\x00")[:-1]
                return drives
            else:
                # Для Unix-систем читаем /proc/mounts или /etc/mtab
                mounts = []
                try:
                    with open("/proc/mounts", "r") as f:
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 2:
                                mounts.append(parts[1])
                except FileNotFoundError:
                    try:
                        with open("/etc/mtab", "r") as f:
                            for line in f:
                                parts = line.split()
                                if len(parts) >= 2:
                                    mounts.append(parts[1])
                    except FileNotFoundError:
                        # Если не удалось прочитать /proc/mounts или /etc/mtab, используем os.listdir("/")
                        for item in os.listdir("/"):
                            if os.path.ismount(f"/{item}"):
                                mounts.append(f"/{item}")
                
                return mounts
        except Exception as e:
            logger.error(f"Ошибка при получении списка смонтированных дисков: {e}")
            return []
    
    @staticmethod
    def is_same_file(file_path1: str, file_path2: str) -> bool:
        """
        Проверка, являются ли два пути одним и тем же файлом
        
        Args:
            file_path1 (str): Первый путь к файлу
            file_path2 (str): Второй путь к файлу
            
        Returns:
            bool: True если пути указывают на один и тот же файл, иначе False
        """
        try:
            # Нормализация путей
            norm_path1 = os.path.normpath(os.path.abspath(file_path1))
            norm_path2 = os.path.normpath(os.path.abspath(file_path2))
            
            # Сравнение путей
            return norm_path1 == norm_path2
        except Exception as e:
            logger.error(f"Ошибка при проверке, являются ли пути {file_path1} и {file_path2} одним и тем же файлом: {e}")
            return False
    
    @staticmethod
    def is_subdirectory(parent_dir: str, child_dir: str) -> bool:
        """
        Проверка, является ли одна директория поддиректорией другой
        
        Args:
            parent_dir (str): Путь к родительской директории
            child_dir (str): Путь к дочерней директории
            
        Returns:
            bool: True если child_dir является поддиректорией parent_dir, иначе False
        """
        try:
            # Нормализация путей
            norm_parent = os.path.normpath(os.path.abspath(parent_dir))
            norm_child = os.path.normpath(os.path.abspath(child_dir))
            
            # Проверка, что norm_child начинается с norm_parent
            return norm_child.startswith(norm_parent)
        except Exception as e:
            logger.error(f"Ошибка при проверке, является ли {child_dir} поддиректорией {parent_dir}: {e}")
            return False
    
    @staticmethod
    def get_common_path(paths: List[str]) -> str:
        """
        Получение общего пути для списка путей
        
        Args:
            paths (List[str]): Список путей
            
        Returns:
            str: Общий путь
        """
        try:
            if not paths:
                return ""
            
            # Нормализация путей
            norm_paths = [os.path.normpath(os.path.abspath(path)) for path in paths]
            
            # Разделение путей на компоненты
            split_paths = [path.split(os.sep) for path in norm_paths]
            
            # Поиск общего префикса
            common_components = []
            for components in zip(*split_paths):
                if len(set(components)) == 1:
                    common_components.append(components[0])
                else:
                    break
            
            # Сборка общего пути
            common_path = os.sep.join(common_components)
            
            return common_path
        except Exception as e:
            logger.error(f"Ошибка при получении общего пути для {paths}: {e}")
            return ""
    
    @staticmethod
    def get_unique_file_name(dir_path: str, file_name: str) -> str:
        """
        Получение уникального имени файла в директории
        
        Args:
            dir_path (str): Путь к директории
            file_name (str): Имя файла
            
        Returns:
            str: Уникальное имя файла
        """
        try:
            # Нормализация путей
            norm_dir_path = os.path.normpath(os.path.abspath(dir_path))
            
            # Проверка, существует ли файл
            file_path = os.path.join(norm_dir_path, file_name)
            if not os.path.exists(file_path):
                return file_name
            
            # Разделение имени файла на имя и расширение
            name, ext = os.path.splitext(file_name)
            
            # Поиск уникального имени
            counter = 1
            while True:
                new_file_name = f"{name}_{counter}{ext}"
                new_file_path = os.path.join(norm_dir_path, new_file_name)
                if not os.path.exists(new_file_path):
                    return new_file_name
                counter += 1
        except Exception as e:
            logger.error(f"Ошибка при получении уникального имени файла для {file_name} в {dir_path}: {e}")
            return file_name
    
    @staticmethod
    def get_unique_dir_name(parent_dir: str, dir_name: str) -> str:
        """
        Получение уникального имени директории в родительской директории
        
        Args:
            parent_dir (str): Путь к родительской директории
            dir_name (str): Имя директории
            
        Returns:
            str: Уникальное имя директории
        """
        try:
            # Нормализация путей
            norm_parent_dir = os.path.normpath(os.path.abspath(parent_dir))
            
            # Проверка, существует ли директория
            dir_path = os.path.join(norm_parent_dir, dir_name)
            if not os.path.exists(dir_path):
                return dir_name
            
            # Поиск уникального имени
            counter = 1
            while True:
                new_dir_name = f"{dir_name}_{counter}"
                new_dir_path = os.path.join(norm_parent_dir, new_dir_name)
                if not os.path.exists(new_dir_path):
                    return new_dir_name
                counter += 1
        except Exception as e:
            logger.error(f"Ошибка при получении уникального имени директории для {dir_name} в {parent_dir}: {e}")
            return dir_name
    
    @staticmethod
    def compare_files(file_path1: str, file_path2: str) -> bool:
        """
        Сравнение двух файлов
        
        Args:
            file_path1 (str): Путь к первому файлу
            file_path2 (str): Путь ко второму файлу
            
        Returns:
            bool: True если файлы идентичны, иначе False
        """
        try:
            # Проверка размеров файлов
            size1 = FileUtils.get_file_size(file_path1)
            size2 = FileUtils.get_file_size(file_path2)
            
            if size1 != size2:
                return False
            
            # Проверка хешей файлов
            hash1 = FileUtils.get_file_hash(file_path1)
            hash2 = FileUtils.get_file_hash(file_path2)
            
            return hash1 == hash2
        except Exception as e:
            logger.error(f"Ошибка при сравнении файлов {file_path1} и {file_path2}: {e}")
            return False
    
    @staticmethod
    def compare_directories(dir_path1: str, dir_path2: str) -> bool:
        """
        Сравнение двух директорий
        
        Args:
            dir_path1 (str): Путь к первой директории
            dir_path2 (str): Путь ко второй директории
            
        Returns:
            bool: True если директории идентичны, иначе False
        """
        try:
            # Получение списков файлов
            files1 = set(FileUtils.get_file_list(dir_path1, recursive=True))
            files2 = set(FileUtils.get_file_list(dir_path2, recursive=True))
            
            # Проверка количества файлов
            if len(files1) != len(files2):
                return False
            
            # Сравнение файлов
            for file_path1 in files1:
                # Получение относительного пути
                rel_path = os.path.relpath(file_path1, dir_path1)
                
                # Формирование пути во второй директории
                file_path2 = os.path.join(dir_path2, rel_path)
                
                # Проверка существования файла
                if file_path2 not in files2:
                    return False
                
                # Сравнение файлов
                if not FileUtils.compare_files(file_path1, file_path2):
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при сравнении директорий {dir_path1} и {dir_path2}: {e}")
            return False
    
    @staticmethod
    def find_files(dir_path: str, pattern: str, recursive: bool = True) -> List[str]:
        """
        Поиск файлов по шаблону
        
        Args:
            dir_path (str): Путь к директории
            pattern (str): Шаблон для поиска
            recursive (bool): Рекурсивный поиск
            
        Returns:
            List[str]: Список найденных файлов
        """
        try:
            # Компиляция регулярного выражения
            regex = re.compile(pattern)
            
            # Поиск файлов
            found_files = []
            
            if recursive:
                for dirpath, dirnames, filenames in os.walk(dir_path):
                    for filename in filenames:
                        if regex.search(filename):
                            found_files.append(os.path.join(dirpath, filename))
            else:
                with os.scandir(dir_path) as entries:
                    for entry in entries:
                        if entry.is_file() and regex.search(entry.name):
                            found_files.append(entry.path)
            
            return found_files
        except Exception as e:
            logger.error(f"Ошибка при поиске файлов по шаблону {pattern} в {dir_path}: {e}")
            return []
    
    @staticmethod
    def find_directories(dir_path: str, pattern: str, recursive: bool = True) -> List[str]:
        """
        Поиск директорий по шаблону
        
        Args:
            dir_path (str): Путь к директории
            pattern (str): Шаблон для поиска
            recursive (bool): Рекурсивный поиск
            
        Returns:
            List[str]: Список найденных директорий
        """
        try:
            # Компиляция регулярного выражения
            regex = re.compile(pattern)
            
            # Поиск директорий
            found_dirs = []
            
            if recursive:
                for dirpath, dirnames, filenames in os.walk(dir_path):
                    for dirname in dirnames:
                        if regex.search(dirname):
                            found_dirs.append(os.path.join(dirpath, dirname))
            else:
                with os.scandir(dir_path) as entries:
                    for entry in entries:
                        if entry.is_dir() and regex.search(entry.name):
                            found_dirs.append(entry.path)
            
            return found_dirs
        except Exception as e:
            logger.error(f"Ошибка при поиске директорий по шаблону {pattern} в {dir_path}: {e}")
            return []
    
    @staticmethod
    def count_files_by_extension(dir_path: str, recursive: bool = True) -> Dict[str, int]:
        """
        Подсчет количества файлов по расширениям
        
        Args:
            dir_path (str): Путь к директории
            recursive (bool): Рекурсивный подсчет
            
        Returns:
            Dict[str, int]: Словарь с количеством файлов по расширениям
        """
        try:
            # Инициализация счетчика
            extension_counts = {}
            
            # Подсчет файлов
            if recursive:
                for dirpath, dirnames, filenames in os.walk(dir_path):
                    for filename in filenames:
                        ext = os.path.splitext(filename)[1].lower()
                        extension_counts[ext] = extension_counts.get(ext, 0) + 1
            else:
                with os.scandir(dir_path) as entries:
                    for entry in entries:
                        if entry.is_file():
                            ext = os.path.splitext(entry.name)[1].lower()
                            extension_counts[ext] = extension_counts.get(ext, 0) + 1
            
            return extension_counts
        except Exception as e:
            logger.error(f"Ошибка при подсчете количества файлов по расширениям в {dir_path}: {e}")
            return {}
    
    @staticmethod
    def get_file_info(file_path: str) -> Dict[str, Any]:
        """
        Получение информации о файле
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            Dict[str, Any]: Информация о файле
        """
        try:
            # Проверка существования файла
            if not os.path.exists(file_path):
                return {}
            
            # Получение статистики файла
            stat = os.stat(file_path)
            
            # Формирование информации о файле
            info = {
                "path": file_path,
                "name": os.path.basename(file_path),
                "name_without_extension": os.path.splitext(os.path.basename(file_path))[0],
                "extension": os.path.splitext(file_path)[1].lower(),
                "size": stat.st_size,
                "size_formatted": FileUtils.format_file_size(stat.st_size),
                "creation_time": stat.st_ctime,
                "creation_time_formatted": FileUtils.format_timestamp(stat.st_ctime),
                "modification_time": stat.st_mtime,
                "modification_time_formatted": FileUtils.format_timestamp(stat.st_mtime),
                "access_time": stat.st_atime,
                "access_time_formatted": FileUtils.format_timestamp(stat.st_atime),
                "is_file": os.path.isfile(file_path),
                "is_dir": os.path.isdir(file_path),
                "is_link": os.path.islink(file_path),
                "is_readable": os.access(file_path, os.R_OK),
                "is_writable": os.access(file_path, os.W_OK),
                "is_executable": os.access(file_path, os.X_OK),
                "permissions": stat.st_mode,
                "owner": FileUtils.get_file_owner(file_path),
                "group": FileUtils.get_file_group(file_path),
                "attributes": FileUtils.get_file_attributes(file_path),
                "hash_md5": FileUtils.get_file_hash(file_path, "md5"),
                "hash_sha1": FileUtils.get_file_hash(file_path, "sha1"),
                "hash_sha256": FileUtils.get_file_hash(file_path, "sha256"),
                "hash_sha512": FileUtils.get_file_hash(file_path, "sha512")
            }
            
            return info
        except Exception as e:
            logger.error(f"Ошибка при получении информации о файле {file_path}: {e}")
            return {}
    
    @staticmethod
    def get_directory_info(dir_path: str) -> Dict[str, Any]:
        """
        Получение информации о директории
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            Dict[str, Any]: Информация о директории
        """
        try:
            # Проверка существования директории
            if not os.path.exists(dir_path):
                return {}
            
            # Получение статистики директории
            stat = os.stat(dir_path)
            
            # Подсчет файлов и поддиректорий
            file_count = 0
            dir_count = 0
            total_size = 0
            
            for dirpath, dirnames, filenames in os.walk(dir_path):
                file_count += len(filenames)
                dir_count += len(dirnames)
                
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(file_path)
                    except:
                        pass
            
            # Формирование информации о директории
            info = {
                "path": dir_path,
                "name": os.path.basename(dir_path),
                "size": total_size,
                "size_formatted": FileUtils.format_file_size(total_size),
                "file_count": file_count,
                "dir_count": dir_count,
                "creation_time": stat.st_ctime,
                "creation_time_formatted": FileUtils.format_timestamp(stat.st_ctime),
                "modification_time": stat.st_mtime,
                "modification_time_formatted": FileUtils.format_timestamp(stat.st_mtime),
                "access_time": stat.st_atime,
                "access_time_formatted": FileUtils.format_timestamp(stat.st_atime),
                "is_file": os.path.isfile(dir_path),
                "is_dir": os.path.isdir(dir_path),
                "is_link": os.path.islink(dir_path),
                "is_readable": os.access(dir_path, os.R_OK),
                "is_writable": os.access(dir_path, os.W_OK),
                "is_executable": os.access(dir_path, os.X_OK),
                "permissions": stat.st_mode,
                "owner": FileUtils.get_file_owner(dir_path),
                "group": FileUtils.get_file_group(dir_path),
                "attributes": FileUtils.get_file_attributes(dir_path),
                "extension_counts": FileUtils.count_files_by_extension(dir_path)
            }
            
            return info
        except Exception as e:
            logger.error(f"Ошибка при получении информации о директории {dir_path}: {e}")
            return {}
    
    @staticmethod
    def open_file(file_path: str) -> bool:
        """
        Открытие файла в ассоциированном приложении
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл успешно открыт, иначе False
        """
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", file_path])
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при открытии файла {file_path}: {e}")
            return False
    
    @staticmethod
    def open_directory(dir_path: str) -> bool:
        """
        Открытие директории в файловом менеджере
        
        Args:
            dir_path (str): Путь к директории
            
        Returns:
            bool: True если директория успешно открыта, иначе False
        """
        try:
            if platform.system() == "Windows":
                os.startfile(dir_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", dir_path])
            else:  # Linux
                subprocess.run(["xdg-open", dir_path])
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при открытии директории {dir_path}: {e}")
            return False
    
    @staticmethod
    def open_file_location(file_path: str) -> bool:
        """
        Открытие расположения файла в файловом менеджере
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если расположение файла успешно открыто, иначе False
        """
        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", "/select,", file_path])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", file_path])
            else:  # Linux
                # Для Linux используем dbus, если доступен
                try:
                    subprocess.run(["dbus-send", "--session", "--dest=org.freedesktop.FileManager1",
                                   "--type=method_call", "/org/freedesktop/FileManager1",
                                   "org.freedesktop.FileManager1.ShowItems",
                                   f"array:string:file://{file_path}", "string:"])
                except:
                    # Если dbus недоступен, открываем родительскую директорию
                    parent_dir = os.path.dirname(file_path)
                    subprocess.run(["xdg-open", parent_dir])
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при открытии расположения файла {file_path}: {e}")
            return False
    
    @staticmethod
    def execute_command(command: str, cwd: str = None, timeout: int = None) -> Tuple[int, str, str]:
        """
        Выполнение команды в командной строке
        
        Args:
            command (str): Команда для выполнения
            cwd (str): Рабочая директория
            timeout (int): Таймаут выполнения в секундах
            
        Returns:
            Tuple[int, str, str]: Код возврата, stdout, stderr
        """
        try:
            # Выполнение команды
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Ожидание завершения с таймаутом
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                return_code = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return_code = -1  # Специальный код для таймаута
            
            return return_code, stdout, stderr
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды {command}: {e}")
            return -1, "", str(e)
    
    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """
        Получение информации о системе
        
        Returns:
            Dict[str, Any]: Информация о системе
        """
        try:
            # Формирование информации о системе
            info = {
                "platform": platform.platform(),
                "system": platform.system(),
                "node": platform.node(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "python_compiler": platform.python_compiler(),
                "python_build": platform.python_build(),
                "architecture": platform.architecture(),
                "uname": platform.uname(),
                "disk_space": {},
                "mounted_drives": FileUtils.get_mounted_drives()
            }
            
            # Получение информации о дисковом пространстве для каждого диска
            for drive in info["mounted_drives"]:
                info["disk_space"][drive] = FileUtils.get_disk_space(drive)
            
            return info
        except Exception as e:
            logger.error(f"Ошибка при получении информации о системе: {e}")
            return {}
    
    @staticmethod
    def get_environment_variables() -> Dict[str, str]:
        """
        Получение переменных окружения
        
        Returns:
            Dict[str, str]: Переменные окружения
        """
        try:
            return dict(os.environ)
        except Exception as e:
            logger.error(f"Ошибка при получении переменных окружения: {e}")
            return {}
    
    @staticmethod
    def get_process_list() -> List[Dict[str, Any]]:
        """
        Получение списка процессов
        
        Returns:
            List[Dict[str, Any]]: Список процессов
        """
        try:
            processes = []
            
            if platform.system() == "Windows":
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'username', 'cmdline']):
                    try:
                        processes.append({
                            "pid": proc.info['pid'],
                            "name": proc.info['name'],
                            "username": proc.info['username'],
                            "cmdline": " ".join(proc.info['cmdline']) if proc.info['cmdline'] else ""
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            else:
                # Для Unix-систем используем ps
                result = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                lines = result.stdout.split("\n")[1:]  # Пропускаем заголовок
                
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 11:
                            processes.append({
                                "pid": int(parts[1]),
                                "username": parts[0],
                                "name": parts[10],
                                "cmdline": " ".join(parts[10:])
                            })
            
            return processes
        except Exception as e:
            logger.error(f"Ошибка при получении списка процессов: {e}")
            return []
    
    @staticmethod
    def kill_process(pid: int) -> bool:
        """
        Завершение процесса
        
        Args:
            pid (int): ID процесса
            
        Returns:
            bool: True если процесс успешно завершен, иначе False
        """
        try:
            if platform.system() == "Windows":
                import psutil
                proc = psutil.Process(pid)
                proc.kill()
            else:
                os.kill(pid, 9)  # SIGKILL
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при завершении процесса с PID {pid}: {e}")
            return False
    
    @staticmethod
    def is_process_running(pid: int) -> bool:
        """
        Проверка, запущен ли процесс
        
        Args:
            pid (int): ID процесса
            
        Returns:
            bool: True если процесс запущен, иначе False
        """
        try:
            if platform.system() == "Windows":
                import psutil
                return psutil.pid_exists(pid)
            else:
                # Отправка сигнала 0 для проверки существования процесса
                os.kill(pid, 0)
                return True
        except Exception:
            return False
    
    @staticmethod
    def get_process_info(pid: int) -> Dict[str, Any]:
        """
        Получение информации о процессе
        
        Args:
            pid (int): ID процесса
            
        Returns:
            Dict[str, Any]: Информация о процессе
        """
        try:
            if platform.system() == "Windows":
                import psutil
                proc = psutil.Process(pid)
                with proc.oneshot():
                    info = {
                        "pid": proc.pid,
                        "name": proc.name(),
                        "username": proc.username(),
                        "cmdline": " ".join(proc.cmdline()) if proc.cmdline() else "",
                        "status": proc.status(),
                        "create_time": proc.create_time(),
                        "create_time_formatted": FileUtils.format_timestamp(proc.create_time()),
                        "cpu_percent": proc.cpu_percent(),
                        "memory_percent": proc.memory_percent(),
                        "memory_info": proc.memory_info()._asdict(),
                        "memory_info_formatted": {
                            k: FileUtils.format_file_size(v) for k, v in proc.memory_info()._asdict().items()
                        },
                        "num_threads": proc.num_threads(),
                        "num_handles": proc.num_handles() if hasattr(proc, 'num_handles') else 0,
                        "exe": proc.exe(),
                        "cwd": proc.cwd(),
                        "environ": dict(proc.environ()),
                        "connections": [conn._asdict() for conn in proc.connections()],
                        "open_files": [f.path for f in proc.open_files()],
                        "threads": [t.id for t in proc.threads()]
                    }
            else:
                # Для Unix-систем используем ps
                result = subprocess.run(["ps", "-p", str(pid), "-o", "pid,user,comm,cmd,stat,start,time,%cpu,%mem,nlwp"], 
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                lines = result.stdout.split("\n")
                
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 10:
                        info = {
                            "pid": int(parts[0]),
                            "username": parts[1],
                            "name": parts[2],
                            "cmdline": " ".join(parts[3:]),
                            "status": parts[4],
                            "cpu_percent": float(parts[7]),
                            "memory_percent": float(parts[8]),
                            "num_threads": int(parts[9])
                        }
                    else:
                        info = {}
                else:
                    info = {}
            
            return info
        except Exception as e:
            logger.error(f"Ошибка при получении информации о процессе с PID {pid}: {e}")
            return {}
    
    @staticmethod
    def run_as_admin(command: str) -> Tuple[int, str, str]:
        """
        Запуск команды с правами администратора
        
        Args:
            command (str): Команда для выполнения
            
        Returns:
            Tuple[int, str, str]: Код возврата, stdout, stderr
        """
        try:
            if platform.system() == "Windows":
                import win32api
                import win32con
                import win32process
                
                # Запуск команды с правами администратора
                result = subprocess.run(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                return result.returncode, result.stdout, result.stderr
            else:
                # Для Unix-систем используем sudo
                result = subprocess.run(
                    ["sudo"] + command.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                return result.returncode, result.stdout, result.stderr
        except Exception as e:
            logger.error(f"Ошибка при запуске команды {command} с правами администратора: {e}")
            return -1, "", str(e)
    
    @staticmethod
    def create_shortcut(target_path: str, shortcut_path: str, arguments: str = "", description: str = "", icon_path: str = "") -> bool:
        """
        Создание ярлыка
        
        Args:
            target_path (str): Путь к целевому файлу
            shortcut_path (str): Путь к ярлыку
            arguments (str): Аргументы командной строки
            description (str): Описание ярлыка
            icon_path (str): Путь к иконке
            
        Returns:
            bool: True если ярлык успешно создан, иначе False
        """
        try:
            if platform.system() == "Windows":
                import win32com.client
                
                # Создание объекта Shell
                shell = win32com.client.Dispatch("WScript.Shell")
                
                # Создание ярлыка
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = target_path
                shortcut.Arguments = arguments
                shortcut.Description = description
                shortcut.IconLocation = icon_path if icon_path else target_path + ", 0"
                shortcut.save()
            else:
                # Для Unix-систем создаем символическую ссылку
                os.symlink(target_path, shortcut_path)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при создании ярлыка для {target_path}: {e}")
            return False
    
    @staticmethod
    def get_file_mimetype(file_path: str) -> str:
        """
        Получение MIME-типа файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: MIME-тип файла
        """
        try:
            import mimetypes
            
            # Инициализация модуля mimetypes
            mimetypes.init()
            
            # Получение MIME-типа
            mime_type, _ = mimetypes.guess_type(file_path)
            
            return mime_type or "application/octet-stream"
        except Exception as e:
            logger.error(f"Ошибка при получении MIME-типа файла {file_path}: {e}")
            return "application/octet-stream"
    
    @staticmethod
    def is_text_file(file_path: str) -> bool:
        """
        Проверка, является ли файл текстовым
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл текстовый, иначе False
        """
        try:
            # Получение MIME-типа
            mime_type = FileUtils.get_file_mimetype(file_path)
            
            # Проверка на текстовый MIME-тип
            return mime_type.startswith("text/") or mime_type in [
                "application/json", "application/xml", "application/javascript",
                "application/x-javascript", "application/x-shellscript"
            ]
        except Exception as e:
            logger.error(f"Ошибка при проверке, является ли файл {file_path} текстовым: {e}")
            return False
    
    @staticmethod
    def is_binary_file(file_path: str) -> bool:
        """
        Проверка, является ли файл бинарным
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл бинарный, иначе False
        """
        return not FileUtils.is_text_file(file_path)
    
    @staticmethod
    def is_image_file(file_path: str) -> bool:
        """
        Проверка, является ли файл изображением
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл изображение, иначе False
        """
        try:
            # Получение MIME-типа
            mime_type = FileUtils.get_file_mimetype(file_path)
            
            # Проверка на MIME-тип изображения
            return mime_type.startswith("image/")
        except Exception as e:
            logger.error(f"Ошибка при проверке, является ли файл {file_path} изображением: {e}")
            return False
    
    @staticmethod
    def is_audio_file(file_path: str) -> bool:
        """
        Проверка, является ли файл аудиофайлом
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл аудиофайл, иначе False
        """
        try:
            # Получение MIME-типа
            mime_type = FileUtils.get_file_mimetype(file_path)
            
            # Проверка на MIME-тип аудиофайла
            return mime_type.startswith("audio/")
        except Exception as e:
            logger.error(f"Ошибка при проверке, является ли файл {file_path} аудиофайлом: {e}")
            return False
    
    @staticmethod
    def is_video_file(file_path: str) -> bool:
        """
        Проверка, является ли файл видеофайлом
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл видеофайл, иначе False
        """
        try:
            # Получение MIME-типа
            mime_type = FileUtils.get_file_mimetype(file_path)
            
            # Проверка на MIME-тип видеофайла
            return mime_type.startswith("video/")
        except Exception as e:
            logger.error(f"Ошибка при проверке, является ли файл {file_path} видеофайлом: {e}")
            return False
    
    @staticmethod
    def is_archive_file(file_path: str) -> bool:
        """
        Проверка, является ли файл архивом
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл архив, иначе False
        """
        try:
            # Получение расширения файла
            ext = FileUtils.get_file_extension(file_path).lower()
            
            # Проверка на расширение архива
            return ext in [
                ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".z",
                ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"
            ]
        except Exception as e:
            logger.error(f"Ошибка при проверке, является ли файл {file_path} архивом: {e}")
            return False
    
    @staticmethod
    def is_executable_file(file_path: str) -> bool:
        """
        Проверка, является ли файл исполняемым
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            bool: True если файл исполняемый, иначе False
        """
        try:
            # Проверка прав на выполнение
            if not FileUtils.is_file_executable(file_path):
                return False
            
            # Получение расширения файла
            ext = FileUtils.get_file_extension(file_path).lower()
            
            # Проверка на расширение исполняемого файла
            if platform.system() == "Windows":
                return ext in [".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf"]
            else:
                # Для Unix-систем проверяем наличие shebang
                with open(file_path, "rb") as f:
                    first_bytes = f.read(2)
                    return first_bytes == b"#!"
        except Exception as e:
            logger.error(f"Ошибка при проверке, является ли файл {file_path} исполняемым: {e}")
            return False
    
    @staticmethod
    def get_file_encoding(file_path: str) -> str:
        """
        Получение кодировки файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            str: Кодировка файла
        """
        try:
            import chardet
            
            # Чтение файла
            with open(file_path, "rb") as f:
                raw_data = f.read()
            
            # Определение кодировки
            result = chardet.detect(raw_data)
            
            return result["encoding"] or "utf-8"
        except Exception as e:
            logger.error(f"Ошибка при получении кодировки файла {file_path}: {e}")
            return "utf-8"
    
    @staticmethod
    def convert_file_encoding(file_path: str, target_encoding: str, source_encoding: str = None) -> bool:
        """
        Конвертация кодировки файла
        
        Args:
            file_path (str): Путь к файлу
            target_encoding (str): Целевая кодировка
            source_encoding (str): Исходная кодировка (если None, определяется автоматически)
            
        Returns:
            bool: True если конвертация успешна, иначе False
        """
        try:
            # Определение исходной кодировки, если не указана
            if source_encoding is None:
                source_encoding = FileUtils.get_file_encoding(file_path)
            
            # Чтение файла в исходной кодировке
            with open(file_path, "r", encoding=source_encoding) as f:
                content = f.read()
            
            # Запись файла в целевой кодировке
            with open(file_path, "w", encoding=target_encoding) as f:
                f.write(content)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при конвертации кодировки файла {file_path}: {e}")
            return False
    
    @staticmethod
    def get_file_line_count(file_path: str) -> int:
        """
        Получение количества строк в файле
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            int: Количество строк в файле
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception as e:
            logger.error(f"Ошибка при получении количества строк в файле {file_path}: {e}")
            return 0
    
    @staticmethod
    def get_file_line(file_path: str, line_number: int) -> str:
        """
        Получение строки из файла по номеру
        
        Args:
            file_path (str): Путь к файлу
            line_number (int): Номер строки (начиная с 1)
            
        Returns:
            str: Строка файла
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if i == line_number:
                        return line.rstrip("\n\r")
            
            return ""
        except Exception as e:
            logger.error(f"Ошибка при получении строки {line_number} из файла {file_path}: {e}")
            return ""
    
    @staticmethod
    def set_file_line(file_path: str, line_number: int, line_content: str) -> bool:
        """
        Установка строки в файле по номеру
        
        Args:
            file_path (str): Путь к файлу
            line_number (int): Номер строки (начиная с 1)
            line_content (str): Содержимое строки
            
        Returns:
            bool: True если строка успешно установлена, иначе False
        """
        try:
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Проверка номера строки
            if line_number < 1 or line_number > len(lines):
                return False
            
            # Установка строки
            lines[line_number - 1] = line_content + "\n"
            
            # Запись файла
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке строки {line_number} в файле {file_path}: {e}")
            return False
    
    @staticmethod
    def insert_file_line(file_path: str, line_number: int, line_content: str) -> bool:
        """
        Вставка строки в файл по номеру
        
        Args:
            file_path (str): Путь к файлу
            line_number (int): Номер строки (начиная с 1)
            line_content (str): Содержимое строки
            
        Returns:
            bool: True если строка успешно вставлена, иначе False
        """
        try:
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Проверка номера строки
            if line_number < 1 or line_number > len(lines) + 1:
                return False
            
            # Вставка строки
            lines.insert(line_number - 1, line_content + "\n")
            
            # Запись файла
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при вставке строки {line_number} в файле {file_path}: {e}")
            return False
    
    @staticmethod
    def delete_file_line(file_path: str, line_number: int) -> bool:
        """
        Удаление строки из файла по номеру
        
        Args:
            file_path (str): Путь к файлу
            line_number (int): Номер строки (начиная с 1)
            
        Returns:
            bool: True если строка успешно удалена, иначе False
        """
        try:
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Проверка номера строки
            if line_number < 1 or line_number > len(lines):
                return False
            
            # Удаление строки
            del lines[line_number - 1]
            
            # Запись файла
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении строки {line_number} из файла {file_path}: {e}")
            return False
    
    @staticmethod
    def find_file_line(file_path: str, pattern: str, case_sensitive: bool = False, regex: bool = False) -> List[int]:
        """
        Поиск строк в файле по шаблону
        
        Args:
            file_path (str): Путь к файлу
            pattern (str): Шаблон для поиска
            case_sensitive (bool): Чувствительность к регистру
            regex (bool): Использование регулярных выражений
            
        Returns:
            List[int]: Список номеров найденных строк
        """
        try:
            # Компиляция регулярного выражения, если необходимо
            if regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern_re = re.compile(pattern, flags)
            else:
                pattern_re = None
            
            # Поиск строк
            found_lines = []
            
            with open(file_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    line = line.rstrip("\n\r")
                    
                    if regex:
                        if pattern_re.search(line):
                            found_lines.append(i)
                    else:
                        if case_sensitive:
                            if pattern in line:
                                found_lines.append(i)
                        else:
                            if pattern.lower() in line.lower():
                                found_lines.append(i)
            
            return found_lines
        except Exception as e:
            logger.error(f"Ошибка при поиске строк в файле {file_path} по шаблону {pattern}: {e}")
            return []
    
    @staticmethod
    def replace_file_line(file_path: str, line_number: int, old_pattern: str, new_pattern: str, case_sensitive: bool = False, regex: bool = False) -> bool:
        """
        Замена текста в строке файла
        
        Args:
            file_path (str): Путь к файлу
            line_number (int): Номер строки (начиная с 1)
            old_pattern (str): Старый шаблон
            new_pattern (str): Новый шаблон
            case_sensitive (bool): Чувствительность к регистру
            regex (bool): Использование регулярных выражений
            
        Returns:
            bool: True если замена успешна, иначе False
        """
        try:
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Проверка номера строки
            if line_number < 1 or line_number > len(lines):
                return False
            
            # Получение строки
            line = lines[line_number - 1].rstrip("\n\r")
            
            # Замена текста
            if regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                new_line = re.sub(old_pattern, new_pattern, line, flags=flags)
            else:
                if case_sensitive:
                    new_line = line.replace(old_pattern, new_pattern)
                else:
                    new_line = line.replace(old_pattern.lower(), new_pattern.lower())
            
            # Установка строки
            lines[line_number - 1] = new_line + "\n"
            
            # Запись файла
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при замене текста в строке {line_number} файла {file_path}: {e}")
            return False
    
    @staticmethod
    def replace_file_lines(file_path: str, old_pattern: str, new_pattern: str, case_sensitive: bool = False, regex: bool = False) -> int:
        """
        Замена текста во всех строках файла
        
        Args:
            file_path (str): Путь к файлу
            old_pattern (str): Старый шаблон
            new_pattern (str): Новый шаблон
            case_sensitive (bool): Чувствительность к регистру
            regex (bool): Использование регулярных выражений
            
        Returns:
            int: Количество замененных строк
        """
        try:
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Замена текста
            replaced_count = 0
            
            for i in range(len(lines)):
                line = lines[i].rstrip("\n\r")
                
                if regex:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    new_line = re.sub(old_pattern, new_pattern, line, flags=flags)
                else:
                    if case_sensitive:
                        new_line = line.replace(old_pattern, new_pattern)
                    else:
                        new_line = line.replace(old_pattern.lower(), new_pattern.lower())
                
                if new_line != line:
                    lines[i] = new_line + "\n"
                    replaced_count += 1
            
            # Запись файла, если были замены
            if replaced_count > 0:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            
            return replaced_count
        except Exception as e:
            logger.error(f"Ошибка при замене текста в файле {file_path}: {e}")
            return 0
    
    @staticmethod
    def get_file_lines_range(file_path: str, start_line: int, end_line: int) -> List[str]:
        """
        Получение диапазона строк из файла
        
        Args:
            file_path (str): Путь к файлу
            start_line (int): Начальная строка (начиная с 1)
            end_line (int): Конечная строка (начиная с 1)
            
        Returns:
            List[str]: Список строк
        """
        try:
            # Проверка номеров строк
            if start_line < 1 or end_line < start_line:
                return []
            
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Проверка номера конечной строки
            if end_line > len(lines):
                end_line = len(lines)
            
            # Получение диапазона строк
            return [lines[i].rstrip("\n\r") for i in range(start_line - 1, end_line)]
        except Exception as e:
            logger.error(f"Ошибка при получении диапазона строк {start_line}-{end_line} из файла {file_path}: {e}")
            return []
    
    @staticmethod
    def get_file_lines_count(file_path: str) -> int:
        """
        Получение количества строк в файле
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            int: Количество строк в файле
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception as e:
            logger.error(f"Ошибка при получении количества строк в файле {file_path}: {e}")
            return 0
    
    @staticmethod
    def get_file_lines(file_path: str) -> List[str]:
        """
        Получение всех строк из файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            List[str]: Список строк
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return [line.rstrip("\n\r") for line in f]
        except Exception as e:
            logger.error(f"Ошибка при получении строк из файла {file_path}: {e}")
            return []
    
    @staticmethod
    def append_file_line(file_path: str, line_content: str) -> bool:
        """
        Добавление строки в конец файла
        
        Args:
            file_path (str): Путь к файлу
            line_content (str): Содержимое строки
            
        Returns:
            bool: True если строка успешно добавлена, иначе False
        """
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line_content + "\n")
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении строки в файл {file_path}: {e}")
            return False
    
    @staticmethod
    def prepend_file_line(file_path: str, line_content: str) -> bool:
        """
        Добавление строки в начало файла
        
        Args:
            file_path (str): Путь к файлу
            line_content (str): Содержимое строки
            
        Returns:
            bool: True если строка успешно добавлена, иначе False
        """
        try:
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Запись файла с новой строкой в начале
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(line_content + "\n" + content)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении строки в начало файла {file_path}: {e}")
            return False
    
    @staticmethod
    def truncate_file(file_path: str, max_size: int) -> bool:
        """
        Усечение файла до указанного размера
        
        Args:
            file_path (str): Путь к файлу
            max_size (int): Максимальный размер файла в байтах
            
        Returns:
            bool: True если файл успешно усечен, иначе False
        """
        try:
            # Проверка размера файла
            file_size = FileUtils.get_file_size(file_path)
            
            if file_size <= max_size:
                return True
            
            # Усечение файла
            with open(file_path, "r+b") as f:
                f.seek(max_size)
                f.truncate()
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при усечении файла {file_path}: {e}")
            return False
    
    @staticmethod
    def truncate_file_lines(file_path: str, max_lines: int) -> bool:
        """
        Усечение файла до указанного количества строк
        
        Args:
            file_path (str): Путь к файлу
            max_lines (int): Максимальное количество строк
            
        Returns:
            bool: True если файл успешно усечен, иначе False
        """
        try:
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Проверка количества строк
            if len(lines) <= max_lines:
                return True
            
            # Усечение файла
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines[-max_lines:])
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при усечении файла {file_path} по количеству строк: {e}")
            return False
    
    @staticmethod
    def split_file(file_path: str, lines_per_file: int, output_dir: str = None) -> List[str]:
        """
        Разделение файла на несколько файлов по количеству строк
        
        Args:
            file_path (str): Путь к файлу
            lines_per_file (int): Количество строк в каждом файле
            output_dir (str): Директория для сохранения файлов
            
        Returns:
            List[str]: Список путей к созданным файлам
        """
        try:
            # Определение директории для сохранения файлов
            if output_dir is None:
                output_dir = FileUtils.get_parent_directory(file_path)
            
            # Создание директории, если она не существует
            FileUtils.create_directory(output_dir)
            
            # Получение имени файла без расширения
            file_name = FileUtils.get_file_name_without_extension(file_path)
            file_ext = FileUtils.get_file_extension(file_path)
            
            # Чтение файла
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Разделение файла
            output_files = []
            total_lines = len(lines)
            file_count = (total_lines + lines_per_file - 1) // lines_per_file
            
            for i in range(file_count):
                start_line = i * lines_per_file
                end_line = min((i + 1) * lines_per_file, total_lines)
                
                # Формирование имени выходного файла
                output_file_name = f"{file_name}_{i + 1}{file_ext}"
                output_file_path = FileUtils.join_paths(output_dir, output_file_name)
                
                # Запись части файла
                with open(output_file_path, "w", encoding="utf-8") as f:
                    f.writelines(lines[start_line:end_line])
                
                output_files.append(output_file_path)
            
            return output_files
        except Exception as e:
            logger.error(f"Ошибка при разделении файла {file_path}: {e}")
   


class TimeUtils:
    """Helper functions for working with timestamps."""

    @staticmethod
    def utc_timestamp() -> float:
        return datetime.datetime.utcnow().timestamp()

    @staticmethod
    def parse_iso8601(value: object) -> float:
        if value in (None, ''):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text_value = str(value).strip()
        if not text_value:
            return 0.0
        normalized = text_value.replace('Z', '+00:00')
        try:
            dt = datetime.datetime.fromisoformat(normalized)
        except ValueError:
            formats = [
                '%Y-%m-%dT%H:%M:%S.%f%z',
                '%Y-%m-%dT%H:%M:%S%z',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d'
            ]
            dt = None
            for fmt in formats:
                try:
                    dt = datetime.datetime.strptime(normalized, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                dt = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()

    @staticmethod
    def format_iso8601(timestamp: float) -> str:
        dt = datetime.datetime.utcfromtimestamp(timestamp).replace(tzinfo=datetime.timezone.utc)
        return dt.isoformat().replace('+00:00', 'Z')

    @staticmethod
    def humanize_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        periods = [
            ('d', 86400),
            ('h', 3600),
            ('m', 60),
            ('s', 1)
        ]
        parts = []
        for suffix, length in periods:
            value, seconds = divmod(seconds, length)
            if value or suffix == 's':
                parts.append(f'{value}{suffix}')
        return ' '.join(parts)


class CryptoUtils:
    """Lightweight helpers for hashing and token generation."""

    @staticmethod
    def hash_text(value: str, algorithm: str = 'sha256', encoding: str = 'utf-8') -> str:
        return CryptoUtils.hash_bytes(value.encode(encoding), algorithm)

    @staticmethod
    def hash_bytes(value: bytes, algorithm: str = 'sha256') -> str:
        try:
            digest = getattr(hashlib, algorithm)()
        except AttributeError as exc:
            raise ValueError(f'Unsupported hash algorithm: {algorithm}') from exc
        digest.update(value)
        return digest.hexdigest()

    @staticmethod
    def generate_token(length: int = 32) -> str:
        return secrets.token_urlsafe(length)


class NetworkUtils:
    """Helpers for quick network connectivity checks."""

    @staticmethod
    def check_port(host: str, port: int, timeout: float = 5.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def is_online(host: str = '8.8.8.8', port: int = 53, timeout: float = 3.0) -> bool:
        return NetworkUtils.check_port(host, port, timeout)

    @staticmethod
    def ensure_trailing_slash(url: str) -> str:
        if not url:
            return ''
        return url if url.endswith('/') else url + '/'
