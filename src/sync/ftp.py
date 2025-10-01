import os
import ftplib
import hashlib
import time
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

from src.sync.utils import FileUtils, TimeUtils, CryptoUtils, NetworkUtils

logger = logging.getLogger(__name__)

class FTPSyncManager:
    """Менеджер синхронизации с FTP-сервером"""
    
    def __init__(self, db_manager, error_handler=None):
        """
        Инициализация менеджера синхронизации с FTP-сервером
        
        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.ftp = None
        self.sync_stats = {
            'uploaded': 0,
            'updated': 0,
            'downloaded': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }
        self.current_sync_id = None
    
    def connect(self, host: str, username: str, password: str, 
               port: int = 21, timeout: int = 30, use_tls: bool = False) -> bool:
        """
        Подключение к FTP-серверу
        
        Args:
            host (str): Адрес FTP-сервера
            username (str): Имя пользователя
            password (str): Пароль
            port (int): Порт FTP-сервера (по умолчанию 21)
            timeout (int): Таймаут подключения в секундах
            use_tls (bool): Использовать ли TLS для защищенного соединения
            
        Returns:
            bool: True, если подключение успешно
        """
        try:
            if use_tls:
                self.ftp = ftplib.FTP_TLS()
                self.ftp.connect(host, port, timeout)
                self.ftp.login(username, password)
                self.ftp.prot_p()  # Включаем защиту данных
            else:
                self.ftp = ftplib.FTP()
                self.ftp.connect(host, port, timeout)
                self.ftp.login(username, password)
            
            logger.info(f"Подключение к FTP-серверу {host} выполнено успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка при подключении к FTP-серверу {host}: {e}")
            return False
    
    def disconnect(self):
        """Отключение от FTP-сервера"""
        if self.ftp:
            try:
                self.ftp.quit()
                logger.info("Отключение от FTP-сервера выполнено успешно")
            except Exception as e:
                logger.error(f"Ошибка при отключении от FTP-сервера: {e}")
            finally:
                self.ftp = None
    
    def ensure_directory(self, remote_path: str) -> bool:
        """
        Создание директории на FTP-сервере, если она не существует
        
        Args:
            remote_path (str): Путь к директории на FTP-сервере
            
        Returns:
            bool: True, если директория существует или создана
        """
        try:
            # Разделяем путь на части
            path_parts = remote_path.split('/')
            current_path = ""
            
            for part in path_parts:
                if not part:  # Пропускаем пустые части (например, в начале пути)
                    continue
                    
                current_path += "/" + part if current_path else part
                
                try:
                    # Пытаемся перейти в директорию
                    self.ftp.cwd(current_path)
                except ftplib.error_perm:
                    # Директория не существует, создаем ее
                    try:
                        self.ftp.mkd(current_path)
                        logger.debug(f"Создана директория: {current_path}")
                        # Переходим в созданную директорию
                        self.ftp.cwd(current_path)
                    except Exception as e:
                        logger.error(f"Ошибка при создании директории {current_path}: {e}")
                        return False
            
            # Возвращаемся в корневую директорию
            self.ftp.cwd("/")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при создании директории {remote_path}: {e}")
            return False
    
    def sync_folders(self, config_id: int, source_path: str, target_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    direction: str = 'upload', delete_mode: bool = True) -> Dict[str, int]:
        """
        Синхронизация папок с FTP-сервером
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_path (str): Путь к папке на FTP-сервере
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            direction (str): Направление синхронизации ('upload' или 'download')
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
            
        Returns:
            Dict[str, int]: Статистика синхронизации
        """
        if not self.ftp:
            error_msg = "FTP-соединение не установлено"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            return self.sync_stats
        
        # Сброс статистики
        self.sync_stats = {
            'uploaded': 0,
            'updated': 0,
            'downloaded': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }
        
        # Запись начала синхронизации в историю
        self.current_sync_id = self.db_manager.add_sync_history(
            config_id=config_id,
            status='in_progress',
            message=f"Начало синхронизации с FTP-сервером: {source_path} <-> {target_path}"
        )
        
        # Проверяем существование исходной папки
        if direction == 'upload' and not os.path.exists(source_path):
            error_msg = f"Исходная папка не существует: {source_path}"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            
            # Обновление истории синхронизации
            if self.current_sync_id:
                self.db_manager.update_sync_history(
                    history_id=self.current_sync_id,
                    status='error',
                    message=error_msg
                )
            
            return self.sync_stats
        
        try:
            if direction == 'upload':
                # Синхронизация из локальной папки на FTP-сервер
                self._sync_upload(config_id, source_path, target_path, callback, delete_mode)
            elif direction == 'download':
                # Синхронизация с FTP-сервера в локальную папку
                self._sync_download(config_id, source_path, target_path, callback, delete_mode)
            else:
                error_msg = f"Неподдерживаемое направление синхронизации: {direction}"
                logger.error(error_msg)
                if callback:
                    callback(f"Ошибка: {error_msg}", "error")
                
                # Обновление истории синхронизации
                if self.current_sync_id:
                    self.db_manager.update_sync_history(
                        history_id=self.current_sync_id,
                        status='error',
                        message=error_msg
                    )
                
                return self.sync_stats
            
            # Обновление истории синхронизации
            if self.current_sync_id:
                total_files = self.sync_stats['uploaded'] + self.sync_stats['updated'] + \
                             self.sync_stats['downloaded'] + self.sync_stats['skipped']
                status = 'success' if self.sync_stats['errors'] == 0 else 'error'
                
                message = f"Синхронизация с FTP-сервером завершена. " \
                         f"Загружено: {self.sync_stats['uploaded']}, " \
                         f"Обновлено: {self.sync_stats['updated']}, " \
                         f"Скачано: {self.sync_stats['downloaded']}, " \
                         f"Удалено: {self.sync_stats['deleted']}, " \
                         f"Пропущено: {self.sync_stats['skipped']}, " \
                         f"Ошибок: {self.sync_stats['errors']}"
                
                self.db_manager.update_sync_history(
                    history_id=self.current_sync_id,
                    status=status,
                    message=message,
                    files_count=total_files
                )
            
            return self.sync_stats
            
        except Exception as e:
            error_msg = f"Ошибка при синхронизации с FTP-сервером: {e}"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка синхронизации: {e}", "error")
            
            self.sync_stats['errors'] += 1
            
            # Обновление истории синхронизации
            if self.current_sync_id:
                self.db_manager.update_sync_history(
                    history_id=self.current_sync_id,
                    status='error',
                    message=error_msg
                )
            
            return self.sync_stats
    
    def _sync_upload(self, config_id: int, source_path: str, target_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    delete_mode: bool = True):
        """
        Синхронизация из локальной папки на FTP-сервер
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_path (str): Путь к папке на FTP-сервере
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
        """
        # Создаем целевую директорию на FTP-сервере, если она не существует
        if not self.ensure_directory(target_path):
            error_msg = f"Не удалось создать директорию на FTP-сервере: {target_path}"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            self.sync_stats['errors'] += 1
            return
        
        # Получаем список файлов на FTP-сервере
        ftp_files = self._get_ftp_files(target_path)
        
        # Синхронизируем файлы из локальной папки на FTP-сервер
        for root, dirs, files in os.walk(source_path):
            # Пропускаем скрытые папки
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                # Пропускаем скрытые файлы
                if filename.startswith('.'):
                    continue
                    
                local_file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(local_file_path, source_path)
                
                # Определяем путь на FTP-сервере
                ftp_path = os.path.join(target_path, rel_path).replace("\\", "/")
                ftp_dir = os.path.dirname(ftp_path)
                ftp_filename = os.path.basename(ftp_path)
                
                # Создаем директорию на FTP-сервере, если необходимо
                if not self.ensure_directory(ftp_dir):
                    error_msg = f"Не удалось создать директорию на FTP-сервере: {ftp_dir}"
                    logger.error(error_msg)
                    if callback:
                        callback(error_msg, "error")
                    self.sync_stats['errors'] += 1
                    continue
                
                # Проверяем, существует ли файл на FTP-сервере
                file_exists = False
                file_mtime = None
                file_size = None
                
                for file_info in ftp_files:
                    if file_info['path'] == ftp_path:
                        file_exists = True
                        file_mtime = file_info['mtime']
                        file_size = file_info['size']
                        break
                
                if file_exists:
                    # Файл существует на FTP-сервере, проверяем, нужно ли обновлять
                    if self._need_upload(local_file_path, file_mtime, file_size, config_id, rel_path):
                        if self._upload_file(local_file_path, ftp_path, callback):
                            self.sync_stats['updated'] += 1
                            
                            # Обновляем состояние файла в базе данных
                            self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                    else:
                        self.sync_stats['skipped'] += 1
                        debug_msg = f"Файл пропущен (без изменений): {rel_path}"
                        logger.debug(debug_msg)
                        if callback:
                            callback(debug_msg, "debug")
                else:
                    # Файла нет на FTP-сервере, загружаем
                    if self._upload_file(local_file_path, ftp_path, callback):
                        self.sync_stats['uploaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
        
        # Удаляем файлы, которые есть на FTP-сервере, но отсутствуют локально
        # ВАЖНО: удаляем только те файлы, которые система сама синхронизировала (есть в file_states)
        if delete_mode:
            # Получаем список файлов, которые были синхронизированы системой
            synced_files = set()
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                synced_files.add(state['file_path'])

            for file_info in ftp_files:
                ftp_path = file_info['path']
                rel_path = os.path.relpath(ftp_path, target_path).replace("\\", "/")
                local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))

                if not os.path.exists(local_file_path):
                    # Удаляем только если этот файл был синхронизирован системой
                    if rel_path in synced_files:
                        if self._delete_file(ftp_path, callback):
                            self.sync_stats['deleted'] += 1

                            # Удаляем состояние файла из базы данных
                            self.db_manager.delete_file_state(config_id, rel_path)
                    else:
                        # Файл не был синхронизирован системой, пропускаем
                        logger.debug(f"Пропущен файл {rel_path} - не был синхронизирован этой системой")
                        if callback:
                            callback(f"Пропущен файл (не синхронизирован системой): {rel_path}", "debug")
    
    def _sync_download(self, config_id: int, target_path: str, source_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None, 
                      delete_mode: bool = True):
        """
        Синхронизация с FTP-сервера в локальную папку
        
        Args:
            config_id (int): ID конфигурации в базе данных
            target_path (str): Путь к локальной папке
            source_path (str): Путь к папке на FTP-сервере
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
        """
        # Создаем целевую папку, если она не существует
        if not os.path.exists(target_path):
            try:
                os.makedirs(target_path)
                info_msg = f"Создана целевая папка: {target_path}"
                logger.info(info_msg)
                if callback:
                    callback(info_msg, "info")
            except Exception as e:
                error_msg = f"Ошибка при создании целевой папки {target_path}: {e}"
                logger.error(error_msg)
                if callback:
                    callback(error_msg, "error")
                self.sync_stats['errors'] += 1
                return
        
        # Получаем список файлов на FTP-сервере
        ftp_files = self._get_ftp_files(source_path)
        
        # Получаем список локальных файлов
        local_files = self._get_local_files(target_path)
        
        # Синхронизируем файлы с FTP-сервера в локальную папку
        for file_info in ftp_files:
            ftp_path = file_info['path']
            rel_path = os.path.relpath(ftp_path, source_path).replace("\\", "/")
            local_file_path = os.path.join(target_path, rel_path)
            
            # Создаем подкаталоги, если необходимо
            target_dir = os.path.dirname(local_file_path)
            if not os.path.exists(target_dir):
                try:
                    os.makedirs(target_dir)
                    logger.debug(f"Создан подкаталог: {target_dir}")
                except Exception as e:
                    error_msg = f"Ошибка при создании подкаталога {target_dir}: {e}"
                    logger.error(error_msg)
                    if callback:
                        callback(error_msg, "error")
                    self.sync_stats['errors'] += 1
                    continue
            
            # Проверяем, существует ли файл локально
            if rel_path not in local_files:
                # Файла нет локально, скачиваем
                if self._download_file(ftp_path, local_file_path, callback):
                    self.sync_stats['downloaded'] += 1
                    
                    # Обновляем состояние файла в базе данных
                    self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
            else:
                # Файл есть локально, проверяем, нужно ли обновлять
                if self._need_download(ftp_path, local_file_path, config_id, rel_path):
                    if self._download_file(ftp_path, local_file_path, callback):
                        self.sync_stats['downloaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                else:
                    self.sync_stats['skipped'] += 1
                    debug_msg = f"Файл пропущен (без изменений): {rel_path}"
                    logger.debug(debug_msg)
                    if callback:
                        callback(debug_msg, "debug")
        
        # Удаляем файлы, которые есть локально, но отсутствуют на FTP-сервере
        # ВАЖНО: удаляем только те файлы, которые система сама синхронизировала (есть в file_states)
        if delete_mode:
            # Получаем список файлов, которые были синхронизированы системой
            synced_files = set()
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                synced_files.add(state['file_path'])

            for rel_path in local_files:
                ftp_path = os.path.join(source_path, rel_path).replace("\\", "/")

                # Проверяем, существует ли файл на FTP-сервере
                file_exists = False
                for file_info in ftp_files:
                    if file_info['path'] == ftp_path:
                        file_exists = True
                        break

                if not file_exists:
                    # Удаляем только если этот файл был синхронизирован системой
                    if rel_path in synced_files:
                        local_file_path = os.path.join(target_path, rel_path)
                        if self._delete_local_file(local_file_path, callback):
                            self.sync_stats['deleted'] += 1

                            # Удаляем состояние файла из базы данных
                            self.db_manager.delete_file_state(config_id, rel_path)
                    else:
                        # Файл не был синхронизирован системой, пропускаем
                        logger.debug(f"Пропущен файл {rel_path} - не был синхронизирован этой системой")
                        if callback:
                            callback(f"Пропущен файл (не синхронизирован системой): {rel_path}", "debug")
    
    def _get_ftp_files(self, remote_path: str) -> List[Dict[str, Any]]:
        """
        Рекурсивное получение списка файлов с FTP-сервера
        
        Args:
            remote_path (str): Путь к папке на FTP-сервере
            
        Returns:
            List[Dict[str, Any]]: Список словарей с информацией о файлах
        """
        files = []
        
        try:
            # Сохраняем текущую директорию
            original_dir = self.ftp.pwd()
            
            # Переходим в указанную директорию
            self.ftp.cwd(remote_path)
            
            # Получаем список файлов и директорий
            items = []
            self.ftp.retrlines('LIST', items.append)
            
            for item in items:
                # Парсим строку LIST
                parts = item.split()
                if len(parts) < 9:
                    continue
                
                # Определяем тип (файл или директория)
                item_type = parts[0][0]
                item_name = ' '.join(parts[8:])
                
                # Пропускаем специальные директории
                if item_name in ['.', '..']:
                    continue
                
                # Формируем полный путь
                item_path = f"{remote_path}/{item_name}" if remote_path != '/' else f"/{item_name}"
                
                if item_type == 'd':  # Директория
                    # Рекурсивно получаем содержимое директории
                    sub_files = self._get_ftp_files(item_path)
                    files.extend(sub_files)
                else:  # Файл
                    # Получаем размер файла
                    try:
                        size = int(parts[4])
                    except (ValueError, IndexError):
                        size = 0
                    
                    # Получаем время модификации
                    try:
                        # Формат времени может отличаться в зависимости от FTP-сервера
                        # Это упрощенный парсинг, который может потребовать доработок
                        month_str = parts[5]
                        day = parts[6]
                        year_or_time = parts[7]
                        
                        # Определяем, это год или время
                        if ':' in year_or_time:
                            # Это время, значит год - текущий
                            time_parts = year_or_time.split(':')
                            hour = int(time_parts[0])
                            minute = int(time_parts[1])
                            
                            # Преобразуем месяц в число
                            month_map = {
                                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                            }
                            month = month_map.get(month_str, 1)
                            
                            # Создаем объект datetime
                            now = datetime.now()
                            year = now.year
                            
                            mtime = datetime(year, month, int(day), hour, minute).timestamp()
                        else:
                            # Это год
                            year = int(year_or_time)
                            
                            # Преобразуем месяц в число
                            month_map = {
                                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                            }
                            month = month_map.get(month_str, 1)
                            
                            # Создаем объект datetime
                            mtime = datetime(year, month, int(day)).timestamp()
                    except Exception as e:
                        logger.error(f"Ошибка при парсинге времени файла {item_name}: {e}")
                        mtime = 0
                    
                    files.append({
                        'path': item_path,
                        'name': item_name,
                        'size': size,
                        'mtime': mtime
                    })
            
            # Возвращаемся в исходную директорию
            self.ftp.cwd(original_dir)
            
            return files
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов с FTP-сервера: {e}")
            return []
    
    def _get_local_files(self, folder_path: str) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка всех файлов в локальной папке и подпапках
        
        Args:
            folder_path (str): Путь к папке
            
        Returns:
            Dict[str, Dict[str, Any]]: Словарь с относительными путями к файлам и их метаданными
        """
        files = {}
        
        for root, dirs, filenames in os.walk(folder_path):
            # Пропускаем скрытые папки
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in filenames:
                # Пропускаем скрытые файлы
                if filename.startswith('.'):
                    continue
                    
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, folder_path)
                
                try:
                    stat = os.stat(file_path)
                    files[rel_path] = {
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'is_dir': False
                    }
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о файле {file_path}: {e}")
        
        return files
    
    def _need_upload(self, local_file_path: str, remote_mtime: Optional[float], 
                    remote_size: Optional[int], config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли загружать/обновлять файл
        
        Args:
            local_file_path (str): Путь к локальному файлу
            remote_mtime (Optional[float]): Время модификации файла на FTP-сервере
            remote_size (Optional[int]): Размер файла на FTP-сервере
            config_id (int): ID конфигурации в базе данных
            rel_path (str): Относительный путь к файлу
            
        Returns:
            bool: True, если файл нужно загрузить/обновить
        """
        try:
            # Получаем информацию о локальном файле
            local_stat = os.stat(local_file_path)
            local_size = local_stat.st_size
            local_mtime = local_stat.st_mtime
            
            # Если удаленный файл не существует, загружаем
            if remote_mtime is None or remote_size is None:
                return True
            
            # Сравниваем размеры
            if local_size != remote_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime > remote_mtime:
                return True
            
            # Проверяем состояние файла в базе данных
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                if state['file_path'] == rel_path:
                    # Если время модификации в базе отличается от текущего, нужно обновить
                    if abs(state['modified_time'] - local_mtime) > 1:  # Допускаем погрешность в 1 секунду
                        return True
                    break
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при проверке необходимости загрузки файла {local_file_path}: {e}")
            return True  # В случае ошибки, считаем что файл нужно обновить
    
    def _need_download(self, remote_path: str, local_file_path: str, 
                      config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли скачивать/обновлять файл
        
        Args:
            remote_path (str): Путь к файлу на FTP-сервере
            local_file_path (str): Путь к локальному файлу
            config_id (int): ID конфигурации в базе данных
            rel_path (str): Относительный путь к файлу
            
        Returns:
            bool: True, если файл нужно скачать/обновить
        """
        try:
            # Получаем информацию о локальном файле
            local_stat = os.stat(local_file_path)
            local_size = local_stat.st_size
            local_mtime = local_stat.st_mtime
            
            # Получаем информацию о файле на FTP-сервере
            remote_dir = os.path.dirname(remote_path)
            remote_filename = os.path.basename(remote_path)
            
            # Сохраняем текущую директорию
            original_dir = self.ftp.pwd()
            
            # Переходим в директорию файла
            self.ftp.cwd(remote_dir)
            
            # Получаем список файлов
            items = []
            self.ftp.retrlines('LIST', items.append)
            
            # Ищем нужный файл
            remote_mtime = None
            remote_size = None
            
            for item in items:
                parts = item.split()
                if len(parts) < 9:
                    continue
                
                item_name = ' '.join(parts[8:])
                
                if item_name == remote_filename:
                    # Получаем размер файла
                    try:
                        remote_size = int(parts[4])
                    except (ValueError, IndexError):
                        remote_size = 0
                    
                    # Получаем время модификации
                    try:
                        month_str = parts[5]
                        day = parts[6]
                        year_or_time = parts[7]
                        
                        # Определяем, это год или время
                        if ':' in year_or_time:
                            # Это время, значит год - текущий
                            time_parts = year_or_time.split(':')
                            hour = int(time_parts[0])
                            minute = int(time_parts[1])
                            
                            # Преобразуем месяц в число
                            month_map = {
                                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                            }
                            month = month_map.get(month_str, 1)
                            
                            # Создаем объект datetime
                            now = datetime.now()
                            year = now.year
                            
                            remote_mtime = datetime(year, month, int(day), hour, minute).timestamp()
                        else:
                            # Это год
                            year = int(year_or_time)
                            
                            # Преобразуем месяц в число
                            month_map = {
                                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                            }
                            month = month_map.get(month_str, 1)
                            
                            # Создаем объект datetime
                            remote_mtime = datetime(year, month, int(day)).timestamp()
                    except Exception as e:
                        logger.error(f"Ошибка при парсинге времени файла {item_name}: {e}")
                        remote_mtime = 0
                    
                    break
            
            # Возвращаемся в исходную директорию
            self.ftp.cwd(original_dir)
            
            # Если файл не найден на сервере, пропускаем
            if remote_mtime is None or remote_size is None:
                return False
            
            # Сравниваем размеры
            if local_size != remote_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime < remote_mtime:
                return True
            
            # Проверяем состояние файла в базе данных
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                if state['file_path'] == rel_path:
                    # Если время модификации в базе отличается от текущего, нужно обновить
                    if abs(state['modified_time'] - local_mtime) > 1:  # Допускаем погрешность в 1 секунду
                        return True
                    break
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при проверке необходимости скачивания файла {local_file_path}: {e}")
            return True  # В случае ошибки, считаем что файл нужно обновить
    
    def _upload_file(self, local_file_path: str, remote_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Загрузка файла на FTP-сервер
        
        Args:
            local_file_path (str): Путь к локальному файлу
            remote_path (str): Путь к файлу на FTP-сервере
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если загрузка успешна
        """
        try:
            with open(local_file_path, 'rb') as f:
                # Определяем директорию на FTP-сервере
                remote_dir = os.path.dirname(remote_path)
                remote_filename = os.path.basename(remote_path)
                
                # Сохраняем текущую директорию
                original_dir = self.ftp.pwd()
                
                # Переходим в целевую директорию
                self.ftp.cwd(remote_dir)
                
                # Загружаем файл
                self.ftp.storbinary(f'STOR {remote_filename}', f)
                
                # Возвращаемся в исходную директорию
                self.ftp.cwd(original_dir)
                
                info_msg = f"Загружен файл на FTP-сервер: {os.path.basename(local_file_path)}"
                logger.info(info_msg)
                if callback:
                    callback(info_msg, "info")
                
                return True
                
        except Exception as e:
            error_msg = f"Ошибка при загрузке файла {local_file_path} на FTP-сервер: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _download_file(self, remote_path: str, local_file_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Скачивание файла с FTP-сервера
        
        Args:
            remote_path (str): Путь к файлу на FTP-сервере
            local_file_path (str): Путь для сохранения файла
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если скачивание успешно
        """
        try:
            # Определяем директорию и имя файла на FTP-сервере
            remote_dir = os.path.dirname(remote_path)
            remote_filename = os.path.basename(remote_path)
            
            # Сохраняем текущую директорию
            original_dir = self.ftp.pwd()
            
            # Переходим в директорию файла
            self.ftp.cwd(remote_dir)
            
            # Создаем директорию для сохранения файла, если она не существует
            output_dir = os.path.dirname(local_file_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Скачиваем файл
            with open(local_file_path, 'wb') as f:
                self.ftp.retrbinary(f'RETR {remote_filename}', f.write)
            
            # Возвращаемся в исходную директорию
            self.ftp.cwd(original_dir)
            
            info_msg = f"Скачан файл с FTP-сервера: {remote_filename}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при скачивании файла {remote_path} с FTP-сервера: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _delete_file(self, remote_path: str, callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Удаление файла с FTP-сервера
        
        Args:
            remote_path (str): Путь к файлу на FTP-сервере
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если удаление успешно
        """
        try:
            # Определяем директорию и имя файла на FTP-сервере
            remote_dir = os.path.dirname(remote_path)
            remote_filename = os.path.basename(remote_path)
            
            # Сохраняем текущую директорию
            original_dir = self.ftp.pwd()
            
            # Переходим в директорию файла
            self.ftp.cwd(remote_dir)
            
            # Удаляем файл
            self.ftp.delete(remote_filename)
            
            # Возвращаемся в исходную директорию
            self.ftp.cwd(original_dir)
            
            info_msg = f"Удален файл с FTP-сервера: {remote_filename}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при удалении файла {remote_path} с FTP-сервера: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _delete_local_file(self, file_path: str, callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Удаление локального файла
        
        Args:
            file_path (str): Путь к файлу
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если удаление успешно
        """
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                info_msg = f"Удален файл: {os.path.basename(file_path)}"
                logger.info(info_msg)
                if callback:
                    callback(info_msg, "info")
                return True
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                info_msg = f"Удалена папка: {os.path.basename(file_path)}"
                logger.info(info_msg)
                if callback:
                    callback(info_msg, "info")
                return True
        except Exception as e:
            error_msg = f"Ошибка при удалении файла/папки {file_path}: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _update_file_state_in_db(self, config_id: int, rel_path: str, file_path: str, sync_status: str):
        """
        Обновление состояния файла в базе данных
        
        Args:
            config_id (int): ID конфигурации
            rel_path (str): Относительный путь к файлу
            file_path (str): Полный путь к файлу
            sync_status (str): Статус синхронизации
        """
        try:
            file_stat = os.stat(file_path)
            
            self.db_manager.update_file_state(
                config_id=config_id,
                file_path=rel_path,
                file_hash=None,  # Для FTP не используем хеш
                modified_time=file_stat.st_mtime,
                sync_status=sync_status
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении состояния файла в базе данных: {e}")
    
    def update_file_states(self, config_id: int, source_path: str, target_path: str, direction: str = 'upload'):
        """
        Обновление состояний файлов в базе данных
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_path (str): Путь к папке на FTP-сервере
            direction (str): Направление синхронизации ('upload' или 'download')
        """
        try:
            if direction == 'upload':
                # Обновляем состояния на основе локальных файлов
                for root, dirs, files in os.walk(source_path):
                    for filename in files:
                        local_file_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(local_file_path, source_path)
                        
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                
                # Удаляем из базы данных записи о файлах, которых больше нет локально
                file_states = self.db_manager.get_file_states(config_id)
                for state in file_states:
                    local_file_path = os.path.join(source_path, state['file_path'])
                    if not os.path.exists(local_file_path):
                        self.db_manager.delete_file_state(config_id, state['file_path'])
            
            elif direction == 'download':
                # Обновляем состояния на основе файлов на FTP-сервере
                ftp_files = self._get_ftp_files(target_path)
                
                for file_info in ftp_files:
                    ftp_path = file_info['path']
                    rel_path = os.path.relpath(ftp_path, target_path).replace("\\", "/")
                    local_file_path = os.path.join(source_path, rel_path)
                    
                    if os.path.exists(local_file_path):
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                
                # Удаляем из базы данных записи о файлах, которых больше нет на FTP-сервере
                file_states = self.db_manager.get_file_states(config_id)
                for state in file_states:
                    ftp_path = os.path.join(target_path, state['file_path']).replace("\\", "/")
                    
                    # Проверяем, существует ли файл на FTP-сервере
                    file_exists = False
                    for file_info in ftp_files:
                        if file_info['path'] == ftp_path:
                            file_exists = True
                            break
                    
                    if not file_exists:
                        self.db_manager.delete_file_state(config_id, state['file_path'])
            
            logger.info(f"Обновлены состояния файлов для конфигурации {config_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении состояний файлов: {e}")
    
    def get_sync_summary(self) -> str:
        """
        Получение сводки о синхронизации
        
        Returns:
            str: Текстовое представление статистики синхронизации
        """
        summary = []
        summary.append("Статистика синхронизации с FTP-сервером:")
        summary.append(f"  Загружено: {self.sync_stats['uploaded']}")
        summary.append(f"  Обновлено: {self.sync_stats['updated']}")
        summary.append(f"  Скачано: {self.sync_stats['downloaded']}")
        summary.append(f"  Удалено: {self.sync_stats['deleted']}")
        summary.append(f"  Пропущено: {self.sync_stats['skipped']}")
        summary.append(f"  Ошибок: {self.sync_stats['errors']}")
        
        return "\n".join(summary)
    
    def preview_sync(self, config_id: int, source_path: str, target_path: str, 
                    direction: str = 'upload') -> Dict[str, Any]:
        """
        Предварительный просмотр синхронизации без выполнения операций
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_path (str): Путь к папке на FTP-сервере
            direction (str): Направление синхронизации ('upload' или 'download')
            
        Returns:
            Dict[str, Any]: Результаты предварительного просмотра
        """
        preview = {
            'to_upload': [],
            'to_update': [],
            'to_download': [],
            'to_delete': [],
            'to_skip': [],
            'errors': []
        }
        
        try:
            if direction == 'upload':
                # Предпросмотр загрузки на FTP-сервер
                if not os.path.exists(source_path):
                    preview['errors'].append(f"Исходная папка не существует: {source_path}")
                    return preview
                
                # Получаем списки файлов
                local_files = self._get_local_files(source_path)
                ftp_files = self._get_ftp_files(target_path)
                
                # Файлы для загрузки
                for rel_path, file_info in local_files.items():
                    # Ищем файл на FTP-сервере
                    ftp_path = os.path.join(target_path, rel_path).replace("\\", "/")
                    remote_mtime = None
                    remote_size = None
                    
                    for ftp_file in ftp_files:
                        if ftp_file['path'] == ftp_path:
                            remote_mtime = ftp_file['mtime']
                            remote_size = ftp_file['size']
                            break
                    
                    if remote_mtime is None or remote_size is None:
                        # Файла нет на FTP-сервере, загружаем
                        preview['to_upload'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
                    else:
                        # Файл есть на FTP-сервере, проверяем, нужно ли обновлять
                        if self._need_upload(os.path.join(source_path, rel_path), remote_mtime, remote_size, config_id, rel_path):
                            preview['to_update'].append({
                                'path': rel_path,
                                'size': file_info['size'],
                                'mtime': file_info['mtime']
                            })
                        else:
                            preview['to_skip'].append({
                                'path': rel_path,
                                'size': file_info['size'],
                                'mtime': file_info['mtime']
                            })
                
                # Файлы для удаления
                for file_info in ftp_files:
                    ftp_path = file_info['path']
                    rel_path = os.path.relpath(ftp_path, target_path).replace("\\", "/")
                    local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))
                    
                    if not os.path.exists(local_file_path):
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
            
            elif direction == 'download':
                # Предпросмотр скачивания с FTP-сервера
                # Получаем списки файлов
                local_files = self._get_local_files(source_path) if os.path.exists(source_path) else {}
                ftp_files = self._get_ftp_files(target_path)
                
                # Файлы для скачивания
                for file_info in ftp_files:
                    ftp_path = file_info['path']
                    rel_path = os.path.relpath(ftp_path, target_path).replace("\\", "/")
                    
                    if rel_path not in local_files:
                        # Файла нет локально, скачиваем
                        preview['to_download'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
                    else:
                        # Файл есть локально, проверяем, нужно ли обновлять
                        local_file_path = os.path.join(source_path, rel_path)
                        if self._need_download(ftp_path, local_file_path, config_id, rel_path):
                            preview['to_download'].append({
                                'path': rel_path,
                                'size': file_info['size'],
                                'mtime': file_info['mtime']
                            })
                        else:
                            preview['to_skip'].append({
                                'path': rel_path,
                                'size': local_files[rel_path]['size'],
                                'mtime': local_files[rel_path]['mtime']
                            })
                
                # Файлы для удаления
                for rel_path in local_files:
                    ftp_path = os.path.join(target_path, rel_path).replace("\\", "/")
                    
                    # Проверяем, существует ли файл на FTP-сервере
                    file_exists = False
                    for file_info in ftp_files:
                        if file_info['path'] == ftp_path:
                            file_exists = True
                            break
                    
                    if not file_exists:
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': local_files[rel_path]['size'],
                            'mtime': local_files[rel_path]['mtime']
                        })
            
            return preview
            
        except Exception as e:
            preview['errors'].append(f"Ошибка при предварительном просмотре синхронизации: {e}")
            return preview

FTPSync = FTPSyncManager
