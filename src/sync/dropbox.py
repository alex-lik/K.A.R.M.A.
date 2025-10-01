import os
import hashlib
import time
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

try:
    import dropbox
    from dropbox.exceptions import ApiError, AuthError
    DROPBOX_AVAILABLE = True
except ImportError:
    DROPBOX_AVAILABLE = False

from src.sync.utils import FileUtils, TimeUtils, CryptoUtils, NetworkUtils

logger = logging.getLogger(__name__)

class DropboxSyncManager:
    """Менеджер синхронизации с Dropbox"""
    
    def __init__(self, db_manager, error_handler=None):
        """
        Инициализация менеджера синхронизации с Dropbox
        
        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.dbx = None
        self.sync_stats = {
            'uploaded': 0,
            'updated': 0,
            'downloaded': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }
        self.current_sync_id = None
    
    def authenticate(self, access_token: str) -> bool:
        """
        Аутентификация в Dropbox
        
        Args:
            access_token (str): Токен доступа
            
        Returns:
            bool: True, если аутентификация успешна
        """
        if not DROPBOX_AVAILABLE:
            logger.error("Модуль Dropbox не установлен. Установите dropbox")
            return False
        
        try:
            # Создаем клиент Dropbox
            self.dbx = dropbox.Dropbox(access_token)
            
            # Проверяем подключение, получая информацию об аккаунте
            self.dbx.users_get_current_account()
            
            logger.info("Аутентификация в Dropbox выполнена успешно")
            return True
            
        except (AuthError, ApiError) as e:
            logger.error(f"Ошибка при аутентификации в Dropbox: {e}")
            return False
    
    def disconnect(self):
        """Отключение от Dropbox"""
        self.dbx = None
        logger.info("Отключение от Dropbox выполнено успешно")
    
    def ensure_directory(self, remote_path: str) -> bool:
        """
        Создание директории в Dropbox, если она не существует
        
        Args:
            remote_path (str): Путь к директории в Dropbox
            
        Returns:
            bool: True, если директория существует или создана
        """
        if not self.dbx:
            logger.error("Dropbox-соединение не установлено")
            return False
        
        try:
            # Проверяем, существует ли директория
            self.dbx.files_get_metadata(remote_path)
            return True
        except ApiError as e:
            error_code = e.error.get_path().get_error().is_not_found()
            if error_code:
                # Директория не существует, создаем ее
                try:
                    self.dbx.files_create_folder_v2(remote_path)
                    logger.debug(f"Создана директория: {remote_path}")
                    return True
                except ApiError as create_error:
                    logger.error(f"Ошибка при создании директории {remote_path}: {create_error}")
                    return False
            else:
                logger.error(f"Ошибка при проверке существования директории {remote_path}: {e}")
                return False
    
    def sync_folders(self, config_id: int, source_path: str, target_info: Dict[str, str], 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    direction: str = 'upload', delete_mode: bool = True) -> Dict[str, int]:
        """
        Синхронизация папок с Dropbox
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_info (Dict[str, str]): Информация о целевом Dropbox-ресурсе {path}
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            direction (str): Направление синхронизации ('upload' или 'download')
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
            
        Returns:
            Dict[str, int]: Статистика синхронизации
        """
        if not self.dbx:
            error_msg = "Dropbox-соединение не установлено"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            return self.sync_stats
        
        target_path = target_info.get('path', '')
        
        if not target_path:
            error_msg = "Не указан путь к папке в Dropbox"
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
            message=f"Начало синхронизации с Dropbox: {source_path} <-> {target_path}"
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
                # Синхронизация из локальной папки в Dropbox
                self._sync_upload(config_id, source_path, target_path, callback, delete_mode)
            elif direction == 'download':
                # Синхронизация из Dropbox в локальную папку
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
                
                message = f"Синхронизация с Dropbox завершена. " \
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
            error_msg = f"Ошибка при синхронизации с Dropbox: {e}"
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
        Синхронизация из локальной папки в Dropbox
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_path (str): Путь к папке в Dropbox
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
        """
        # Создаем целевую директорию в Dropbox, если она не существует
        if not self.ensure_directory(target_path):
            error_msg = f"Не удалось создать директорию в Dropbox: {target_path}"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            self.sync_stats['errors'] += 1
            return
        
        # Получаем список файлов в Dropbox
        dropbox_files = self._get_dropbox_files(target_path)
        
        # Синхронизируем файлы из локальной папки в Dropbox
        for root, dirs, files in os.walk(source_path):
            # Пропускаем скрытые папки
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                # Пропускаем скрытые файлы
                if filename.startswith('.'):
                    continue
                    
                local_file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(local_file_path, source_path)
                
                # Определяем путь в Dropbox
                dropbox_path = os.path.join(target_path, rel_path).replace("\\", "/")
                
                # Проверяем, существует ли файл в Dropbox
                file_exists = False
                file_mtime = None
                file_size = None
                file_hash = None
                
                for file_info in dropbox_files:
                    if file_info['path'] == dropbox_path:
                        file_exists = True
                        file_mtime = file_info['mtime']
                        file_size = file_info['size']
                        file_hash = file_info['hash']
                        break
                
                if file_exists:
                    # Файл существует в Dropbox, проверяем, нужно ли обновлять
                    if self._need_upload(local_file_path, file_mtime, file_size, file_hash, config_id, rel_path):
                        if self._upload_file(local_file_path, dropbox_path, callback):
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
                    # Файла нет в Dropbox, загружаем
                    if self._upload_file(local_file_path, dropbox_path, callback):
                        self.sync_stats['uploaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
        
        # Удаляем файлы, которые есть в Dropbox, но отсутствуют локально
        if delete_mode:
            for file_info in dropbox_files:
                dropbox_path = file_info['path']
                
                # Пропускаем файлы, которые не соответствуют целевому пути
                if not dropbox_path.startswith(target_path):
                    continue
                
                # Определяем относительный путь
                rel_path = dropbox_path[len(target_path):].lstrip('/')
                local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))
                
                if not os.path.exists(local_file_path):
                    if self._delete_file(dropbox_path, callback):
                        self.sync_stats['deleted'] += 1
                        
                        # Удаляем состояние файла из базы данных
                        self.db_manager.delete_file_state(config_id, rel_path)
    
    def _sync_download(self, config_id: int, target_path: str, source_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None, 
                      delete_mode: bool = True):
        """
        Синхронизация из Dropbox в локальную папку
        
        Args:
            config_id (int): ID конфигурации в базе данных
            target_path (str): Путь к локальной папке
            source_path (str): Путь к папке в Dropbox
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
        
        # Получаем список файлов в Dropbox
        dropbox_files = self._get_dropbox_files(source_path)
        
        # Получаем список локальных файлов
        local_files = self._get_local_files(target_path)
        
        # Синхронизируем файлы из Dropbox в локальную папку
        for file_info in dropbox_files:
            dropbox_path = file_info['path']
            
            # Пропускаем файлы, которые не соответствуют исходному пути
            if not dropbox_path.startswith(source_path):
                continue
            
            # Определяем относительный путь
            rel_path = dropbox_path[len(source_path):].lstrip('/')
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
                if self._download_file(dropbox_path, local_file_path, callback):
                    self.sync_stats['downloaded'] += 1
                    
                    # Обновляем состояние файла в базе данных
                    self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
            else:
                # Файл есть локально, проверяем, нужно ли обновлять
                if self._need_download(dropbox_path, local_file_path, config_id, rel_path):
                    if self._download_file(dropbox_path, local_file_path, callback):
                        self.sync_stats['downloaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                else:
                    self.sync_stats['skipped'] += 1
                    debug_msg = f"Файл пропущен (без изменений): {rel_path}"
                    logger.debug(debug_msg)
                    if callback:
                        callback(debug_msg, "debug")
        
        # Удаляем файлы, которые есть локально, но отсутствуют в Dropbox
        if delete_mode:
            for rel_path in local_files:
                dropbox_path = os.path.join(source_path, rel_path).replace("\\", "/")
                
                # Проверяем, существует ли файл в Dropbox
                file_exists = False
                for file_info in dropbox_files:
                    if file_info['path'] == dropbox_path:
                        file_exists = True
                        break
                
                if not file_exists:
                    local_file_path = os.path.join(target_path, rel_path)
                    if self._delete_local_file(local_file_path, callback):
                        self.sync_stats['deleted'] += 1
                        
                        # Удаляем состояние файла из базы данных
                        self.db_manager.delete_file_state(config_id, rel_path)
    
    def _get_dropbox_files(self, remote_path: str) -> List[Dict[str, Any]]:
        """
        Рекурсивное получение списка файлов из Dropbox
        
        Args:
            remote_path (str): Путь к папке в Dropbox
            
        Returns:
            List[Dict[str, Any]]: Список словарей с информацией о файлах
        """
        files = []
        
        try:
            # Получаем список файлов и папок
            result = self.dbx.files_list_folder(remote_path)
            
            while True:
                for entry in result.entries:
                    if isinstance(entry, dropbox.files.FolderMetadata):
                        # Рекурсивно получаем содержимое папки
                        sub_files = self._get_dropbox_files(entry.path_lower)
                        files.extend(sub_files)
                    elif isinstance(entry, dropbox.files.FileMetadata):
                        files.append({
                            'path': entry.path_lower,
                            'name': entry.name,
                            'size': entry.size,
                            'mtime': entry.server_modified.timestamp(),
                            'hash': entry.content_hash
                        })
                
                # Проверяем, есть ли еще файлы
                if not result.has_more:
                    break
                
                # Получаем следующую порцию файлов
                result = self.dbx.files_list_folder_continue(result.cursor)
            
            return files
            
        except ApiError as e:
            logger.error(f"Ошибка при получении списка файлов из Dropbox: {e}")
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
                    remote_size: Optional[int], remote_hash: Optional[str], 
                    config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли загружать/обновлять файл
        
        Args:
            local_file_path (str): Путь к локальному файлу
            remote_mtime (Optional[float]): Время модификации файла в Dropbox
            remote_size (Optional[int]): Размер файла в Dropbox
            remote_hash (Optional[str]): Хеш файла в Dropbox
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
            if remote_mtime is None or remote_size is None or remote_hash is None:
                return True
            
            # Сравниваем размеры
            if local_size != remote_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime > remote_mtime:
                return True
            
            # Сравниваем хеш файла
            local_hash = self.calculate_file_hash(local_file_path)
            if local_hash != remote_hash:
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
    
    def _need_download(self, dropbox_path: str, local_file_path: str, 
                      config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли скачивать/обновлять файл
        
        Args:
            dropbox_path (str): Путь к файлу в Dropbox
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
            
            # Получаем информацию о файле в Dropbox
            try:
                metadata = self.dbx.files_get_metadata(dropbox_path)
                if isinstance(metadata, dropbox.files.FileMetadata):
                    remote_size = metadata.size
                    remote_mtime = metadata.server_modified.timestamp()
                    remote_hash = metadata.content_hash
                else:
                    # Это не файл, а папка
                    return False
            except ApiError:
                # Файл не найден в Dropbox
                return False
            
            # Сравниваем размеры
            if local_size != remote_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime < remote_mtime:
                return True
            
            # Сравниваем хеш файла
            local_hash = self.calculate_file_hash(local_file_path)
            if local_hash != remote_hash:
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
    
    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """
        Вычисление хеша файла для сравнения с Dropbox
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            Optional[str]: Хеш файла в формате Dropbox или None в случае ошибки
        """
        try:
            # Dropbox использует блочное хеширование (block-hash)
            # Для файлов размером до 4 МБ это просто SHA-256
            # Для больших файлов это хеш от конкатенации SHA-256 каждого блока размером 4 МБ
            
            BLOCK_SIZE = 4 * 1024 * 1024  # 4 МБ
            
            with open(file_path, 'rb') as f:
                file_size = os.path.getsize(file_path)
                
                if file_size <= BLOCK_SIZE:
                    # Для файлов размером до 4 МБ
                    data = f.read()
                    return hashlib.sha256(data).hexdigest()
                else:
                    # Для больших файлов
                    hashes = []
                    while True:
                        data = f.read(BLOCK_SIZE)
                        if not data:
                            break
                        hashes.append(hashlib.sha256(data).digest())
                    
                    # Вычисляем хеш от конкатенации хешей блоков
                    combined_hash = b''.join(hashes)
                    return hashlib.sha256(combined_hash).hexdigest()
                
        except Exception as e:
            logger.error(f"Ошибка при вычислении хеша файла {file_path}: {e}")
            return None
    
    def _upload_file(self, local_file_path: str, dropbox_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Загрузка файла в Dropbox
        
        Args:
            local_file_path (str): Путь к локальному файлу
            dropbox_path (str): Путь к файлу в Dropbox
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если загрузка успешна
        """
        try:
            # Определяем размер файла для выбора метода загрузки
            file_size = os.path.getsize(local_file_path)
            
            # Для файлов размером более 150 МБ используем загрузку по частям
            CHUNK_SIZE = 150 * 1024 * 1024  # 150 МБ
            
            if file_size <= CHUNK_SIZE:
                # Простая загрузка для небольших файлов
                with open(local_file_path, 'rb') as f:
                    self.dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            else:
                # Загрузка по частям для больших файлов
                with open(local_file_path, 'rb') as f:
                    # Начинаем сеанс загрузки
                    session_start_result = self.dbx.files_upload_session_start(f.read(CHUNK_SIZE))
                    session_id = session_start_result.session_id
                    
                    # Загружаем оставшиеся части
                    offset = f.tell()
                    while offset < file_size:
                        chunk_size = min(CHUNK_SIZE, file_size - offset)
                        data = f.read(chunk_size)
                        
                        if offset + chunk_size < file_size:
                            # Промежуточная часть
                            self.dbx.files_upload_session_append_v2(data, session_id, offset)
                        else:
                            # Последняя часть, завершаем загрузку
                            cursor = dropbox.files.UploadSessionCursor(
                                session_id=session_id,
                                offset=offset
                            )
                            commit = dropbox.files.CommitInfo(
                                path=dropbox_path,
                                mode=dropbox.files.WriteMode.overwrite
                            )
                            self.dbx.files_upload_session_finish(data, cursor, commit)
                        
                        offset += chunk_size
            
            info_msg = f"Загружен файл в Dropbox: {os.path.basename(local_file_path)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
                
        except ApiError as e:
            error_msg = f"Ошибка при загрузке файла {local_file_path} в Dropbox: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _download_file(self, dropbox_path: str, local_file_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Скачивание файла из Dropbox
        
        Args:
            dropbox_path (str): Путь к файлу в Dropbox
            local_file_path (str): Путь для сохранения файла
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если скачивание успешно
        """
        try:
            # Создаем директорию для сохранения файла, если она не существует
            output_dir = os.path.dirname(local_file_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Скачиваем файл
            metadata, response = self.dbx.files_download(dropbox_path)
            
            with open(local_file_path, 'wb') as f:
                f.write(response.content)
            
            info_msg = f"Скачан файл из Dropbox: {os.path.basename(dropbox_path)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except ApiError as e:
            error_msg = f"Ошибка при скачивании файла {dropbox_path} из Dropbox: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _delete_file(self, dropbox_path: str, callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Удаление файла из Dropbox
        
        Args:
            dropbox_path (str): Путь к файлу в Dropbox
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если удаление успешно
        """
        try:
            # Удаляем файл
            self.dbx.files_delete_v2(dropbox_path)
            
            info_msg = f"Удален файл из Dropbox: {os.path.basename(dropbox_path)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except ApiError as e:
            error_msg = f"Ошибка при удалении файла {dropbox_path} из Dropbox: {e}"
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
                file_hash=None,  # Для Dropbox не используем хеш
                modified_time=file_stat.st_mtime,
                sync_status=sync_status
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении состояния файла в базе данных: {e}")
    
    def update_file_states(self, config_id: int, source_path: str, target_info: Dict[str, str], direction: str = 'upload'):
        """
        Обновление состояний файлов в базе данных
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_info (Dict[str, str]): Информация о целевом Dropbox-ресурсе {path}
            direction (str): Направление синхронизации ('upload' или 'download')
        """
        try:
            target_path = target_info.get('path', '')
            
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
                # Обновляем состояния на основе файлов в Dropbox
                dropbox_files = self._get_dropbox_files(target_path)
                
                for file_info in dropbox_files:
                    dropbox_path = file_info['path']
                    
                    # Пропускаем файлы, которые не соответствуют целевому пути
                    if not dropbox_path.startswith(target_path):
                        continue
                    
                    # Определяем относительный путь
                    rel_path = dropbox_path[len(target_path):].lstrip('/')
                    local_file_path = os.path.join(source_path, rel_path)
                    
                    if os.path.exists(local_file_path):
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                
                # Удаляем из базы данных записи о файлах, которых больше нет в Dropbox
                file_states = self.db_manager.get_file_states(config_id)
                for state in file_states:
                    dropbox_path = os.path.join(target_path, state['file_path']).replace("\\", "/")
                    
                    # Проверяем, существует ли файл в Dropbox
                    file_exists = False
                    for file_info in dropbox_files:
                        if file_info['path'] == dropbox_path:
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
        summary.append("Статистика синхронизации с Dropbox:")
        summary.append(f"  Загружено: {self.sync_stats['uploaded']}")
        summary.append(f"  Обновлено: {self.sync_stats['updated']}")
        summary.append(f"  Скачано: {self.sync_stats['downloaded']}")
        summary.append(f"  Удалено: {self.sync_stats['deleted']}")
        summary.append(f"  Пропущено: {self.sync_stats['skipped']}")
        summary.append(f"  Ошибок: {self.sync_stats['errors']}")
        
        return "\n".join(summary)
    
    def preview_sync(self, config_id: int, source_path: str, target_info: Dict[str, str], 
                    direction: str = 'upload') -> Dict[str, Any]:
        """
        Предварительный просмотр синхронизации без выполнения операций
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_info (Dict[str, str]): Информация о целевом Dropbox-ресурсе {path}
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
            target_path = target_info.get('path', '')
            
            if direction == 'upload':
                # Предпросмотр загрузки в Dropbox
                if not os.path.exists(source_path):
                    preview['errors'].append(f"Исходная папка не существует: {source_path}")
                    return preview
                
                # Получаем списки файлов
                local_files = self._get_local_files(source_path)
                dropbox_files = self._get_dropbox_files(target_path)
                
                # Файлы для загрузки
                for rel_path, file_info in local_files.items():
                    # Ищем файл в Dropbox
                    dropbox_path = os.path.join(target_path, rel_path).replace("\\", "/")
                    remote_mtime = None
                    remote_size = None
                    remote_hash = None
                    
                    for file_info in dropbox_files:
                        if file_info['path'] == dropbox_path:
                            remote_mtime = file_info['mtime']
                            remote_size = file_info['size']
                            remote_hash = file_info['hash']
                            break
                    
                    if remote_mtime is None or remote_size is None or remote_hash is None:
                        # Файла нет в Dropbox, загружаем
                        preview['to_upload'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
                    else:
                        # Файл есть в Dropbox, проверяем, нужно ли обновлять
                        if self._need_upload(os.path.join(source_path, rel_path), remote_mtime, remote_size, remote_hash, config_id, rel_path):
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
                for file_info in dropbox_files:
                    dropbox_path = file_info['path']
                    
                    # Пропускаем файлы, которые не соответствуют целевому пути
                    if not dropbox_path.startswith(target_path):
                        continue
                    
                    # Определяем относительный путь
                    rel_path = dropbox_path[len(target_path):].lstrip('/')
                    local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))
                    
                    if not os.path.exists(local_file_path):
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
            
            elif direction == 'download':
                # Предпросмотр скачивания из Dropbox
                # Получаем списки файлов
                local_files = self._get_local_files(source_path) if os.path.exists(source_path) else {}
                dropbox_files = self._get_dropbox_files(target_path)
                
                # Файлы для скачивания
                for file_info in dropbox_files:
                    dropbox_path = file_info['path']
                    
                    # Пропускаем файлы, которые не соответствуют целевому пути
                    if not dropbox_path.startswith(target_path):
                        continue
                    
                    # Определяем относительный путь
                    rel_path = dropbox_path[len(target_path):].lstrip('/')
                    
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
                        if self._need_download(dropbox_path, local_file_path, config_id, rel_path):
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
                    dropbox_path = os.path.join(target_path, rel_path).replace("\\", "/")
                    
                    # Проверяем, существует ли файл в Dropbox
                    file_exists = False
                    for file_info in dropbox_files:
                        if file_info['path'] == dropbox_path:
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

DropboxSync = DropboxSyncManager
