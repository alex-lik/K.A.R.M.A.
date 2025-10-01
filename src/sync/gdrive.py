import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

from src.sync.utils import FileUtils, TimeUtils, CryptoUtils, NetworkUtils

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    import io
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False

logger = logging.getLogger(__name__)

class GoogleDriveSyncManager:
    """Менеджер синхронизации с Google Drive"""
    
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    def __init__(self, db_manager, error_handler=None):
        """
        Инициализация менеджера синхронизации с Google Drive
        
        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.service = None
        self.sync_stats = {
            'uploaded': 0,
            'updated': 0,
            'downloaded': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }
        self.current_sync_id = None
    
    def authenticate(self, credentials_data: Optional[Dict[str, str]] = None, 
                    service_account_file: Optional[str] = None, 
                    token_file: Optional[str] = None) -> bool:
        """
        Аутентификация в Google Drive
        
        Args:
            credentials_data (Optional[Dict[str, str]]): Данные учетных записи (OAuth2)
            service_account_file (Optional[str]): Путь к файлу сервисного аккаунта
            token_file (Optional[str]): Путь к файлу токена
            
        Returns:
            bool: True, если аутентификация успешна
        """
        if not GOOGLE_DRIVE_AVAILABLE:
            logger.error("Модули Google Drive не установлены. Установите google-api-python-client и google-auth-*")
            return False
        
        try:
            if service_account_file and os.path.exists(service_account_file):
                # Аутентификация через сервисный аккаунт
                credentials = service_account.Credentials.from_service_account_file(
                    service_account_file, scopes=self.SCOPES
                )
                self.service = build('drive', 'v3', credentials=credentials)
                logger.info("Аутентификация через сервисный аккаунт выполнена успешно")
                return True
            
            elif token_file and os.path.exists(token_file):
                # Аутентификация через сохраненный токен
                credentials = Credentials.from_authorized_user_file(token_file, self.SCOPES)
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    # Сохраняем обновленный токен
                    with open(token_file, 'w') as token:
                        token.write(credentials.to_json())
                self.service = build('drive', 'v3', credentials=credentials)
                logger.info("Аутентификация через сохраненный токен выполнена успешно")
                return True
            
            elif credentials_data:
                # Аутентификация через OAuth2
                if 'client_id' in credentials_data and 'client_secret' in credentials_data:
                    # Создаем временный файл client_secret.json
                    client_secret = {
                        "installed": {
                            "client_id": credentials_data['client_id'],
                            "client_secret": credentials_data['client_secret'],
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://localhost"]
                        }
                    }
                    
                    with open('client_secret.json', 'w') as f:
                        json.dump(client_secret, f)
                    
                    flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', self.SCOPES)
                    credentials = flow.run_local_server(port=0)
                    
                    # Удаляем временный файл
                    os.remove('client_secret.json')
                    
                    # Сохраняем токен для будущего использования
                    token_file = token_file or 'gdrive_token.json'
                    with open(token_file, 'w') as token:
                        token.write(credentials.to_json())
                    
                    self.service = build('drive', 'v3', credentials=credentials)
                    logger.info("Аутентификация через OAuth2 выполнена успешно")
                    return True
            
            logger.error("Не удалось выполнить аутентификацию: недостаточно данных")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при аутентификации в Google Drive: {e}")
            return False
    
    def get_or_create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """
        Получение или создание папки в Google Drive
        
        Args:
            folder_name (str): Имя папки
            parent_id (Optional[str]): ID родительской папки
            
        Returns:
            Optional[str]: ID папки
        """
        try:
            # Ищем папку по имени
            query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            response = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            folders = response.get('files', [])
            
            if folders:
                folder_id = folders[0].get('id')
                logger.debug(f"Найдена существующая папка: {folder_name} (ID: {folder_id})")
                return folder_id
            
            # Если папка не найдена, создаем ее
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            logger.info(f"Создана новая папка: {folder_name} (ID: {folder_id})")
            return folder_id
            
        except Exception as e:
            logger.error(f"Ошибка при получении/создании папки {folder_name}: {e}")
            return None
    
    def sync_folders(self, config_id: int, source_path: str, target_folder_id: str, 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    direction: str = 'upload', delete_mode: bool = True) -> Dict[str, int]:
        """
        Синхронизация папок с Google Drive
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_folder_id (str): ID папки в Google Drive
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            direction (str): Направление синхронизации ('upload' или 'download')
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
            
        Returns:
            Dict[str, int]: Статистика синхронизации
        """
        if not self.service:
            error_msg = "Сервис Google Drive не инициализирован"
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
            message=f"Начало синхронизации с Google Drive: {source_path} <-> {target_folder_id}"
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
                # Синхронизация из локальной папки в Google Drive
                self._sync_upload(config_id, source_path, target_folder_id, callback, delete_mode)
            elif direction == 'download':
                # Синхронизация из Google Drive в локальную папку
                self._sync_download(config_id, source_path, target_folder_id, callback, delete_mode)
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
                
                message = f"Синхронизация с Google Drive завершена. " \
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
            error_msg = f"Ошибка при синхронизации с Google Drive: {e}"
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
    
    def _sync_upload(self, config_id: int, source_path: str, target_folder_id: str, 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    delete_mode: bool = True):
        """
        Синхронизация из локальной папки в Google Drive
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_folder_id (str): ID папки в Google Drive
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
        """
        # Получаем список файлов в Google Drive
        drive_files = self._get_drive_files(target_folder_id)
        
        # Синхронизируем файлы из локальной папки в Google Drive
        for root, dirs, files in os.walk(source_path):
            # Пропускаем скрытые папки
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                # Пропускаем скрытые файлы
                if filename.startswith('.'):
                    continue
                    
                local_file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(local_file_path, source_path)
                
                # Определяем путь в Google Drive
                drive_path_parts = rel_path.split(os.sep)
                drive_parent_id = target_folder_id
                
                # Создаем структуру папок в Google Drive
                for folder_name in drive_path_parts[:-1]:
                    drive_parent_id = self.get_or_create_folder(folder_name, drive_parent_id)
                    if not drive_parent_id:
                        error_msg = f"Не удалось создать папку: {folder_name}"
                        logger.error(error_msg)
                        if callback:
                            callback(error_msg, "error")
                        self.sync_stats['errors'] += 1
                        continue
                
                # Имя файла в Google Drive
                drive_file_name = drive_path_parts[-1]
                
                # Проверяем, существует ли файл в Google Drive
                file_id = None
                for fid, file_info in drive_files.items():
                    if file_info['name'] == drive_file_name and file_info['parent_id'] == drive_parent_id:
                        file_id = fid
                        break
                
                if file_id:
                    # Файл существует в Google Drive, проверяем, нужно ли обновлять
                    if self._need_upload(local_file_path, file_id, config_id, rel_path):
                        if self._upload_file(local_file_path, drive_file_name, drive_parent_id, file_id, callback):
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
                    # Файла нет в Google Drive, загружаем
                    if self._upload_file(local_file_path, drive_file_name, drive_parent_id, None, callback):
                        self.sync_stats['uploaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
        
        # Удаляем файлы, которые есть в Google Drive, но отсутствуют локально
        if delete_mode:
            for file_id, file_info in drive_files.items():
                rel_path = file_info['rel_path']
                local_file_path = os.path.join(source_path, rel_path)
                
                if not os.path.exists(local_file_path):
                    if self._delete_file(file_id, callback):
                        self.sync_stats['deleted'] += 1
                        
                        # Удаляем состояние файла из базы данных
                        self.db_manager.delete_file_state(config_id, rel_path)
    
    def _sync_download(self, config_id: int, target_path: str, source_folder_id: str, 
                     callback: Optional[Callable[[str, str], None]] = None, 
                     delete_mode: bool = True):
        """
        Синхронизация из Google Drive в локальную папку
        
        Args:
            config_id (int): ID конфигурации в базе данных
            target_path (str): Путь к локальной папке
            source_folder_id (str): ID папки в Google Drive
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
        
        # Получаем список файлов в Google Drive
        drive_files = self._get_drive_files(source_folder_id)
        
        # Получаем список локальных файлов
        local_files = self._get_local_files(target_path)
        
        # Синхронизируем файлы из Google Drive в локальную папку
        for file_id, file_info in drive_files.items():
            rel_path = file_info['rel_path']
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
                if self._download_file(file_id, local_file_path, callback):
                    self.sync_stats['downloaded'] += 1
                    
                    # Обновляем состояние файла в базе данных
                    self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
            else:
                # Файл есть локально, проверяем, нужно ли обновлять
                if self._need_download(file_id, local_file_path, config_id, rel_path):
                    if self._download_file(file_id, local_file_path, callback):
                        self.sync_stats['downloaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                else:
                    self.sync_stats['skipped'] += 1
                    debug_msg = f"Файл пропущен (без изменений): {rel_path}"
                    logger.debug(debug_msg)
                    if callback:
                        callback(debug_msg, "debug")
        
        # Удаляем файлы, которые есть локально, но отсутствуют в Google Drive
        if delete_mode:
            for rel_path in local_files:
                if rel_path not in {info['rel_path'] for info in drive_files.values()}:
                    local_file_path = os.path.join(target_path, rel_path)
                    if self._delete_local_file(local_file_path, callback):
                        self.sync_stats['deleted'] += 1
                        
                        # Удаляем состояние файла из базы данных
                        self.db_manager.delete_file_state(config_id, rel_path)
    
    def _get_drive_files(self, folder_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка файлов в папке Google Drive
        
        Args:
            folder_id (str): ID папки в Google Drive
            
        Returns:
            Dict[str, Dict[str, Any]]: Словарь с информацией о файлах {file_id: file_info}
        """
        drive_files = {}
        
        try:
            # Рекурсивно получаем все файлы в папке и подпапках
            query = f"'{folder_id}' in parents and trashed=false"
            page_token = None
            
            while True:
                response = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, parents, mimeType, modifiedTime, size)',
                    pageToken=page_token
                ).execute()
                
                files = response.get('files', [])
                
                for file in files:
                    file_id = file.get('id')
                    file_name = file.get('name')
                    parent_id = file.get('parents', [None])[0]
                    mime_type = file.get('mimeType')
                    modified_time = file.get('modifiedTime')
                    size = file.get('size')
                    
                    # Если это папка, рекурсивно получаем ее содержимое
                    if mime_type == 'application/vnd.google-apps.folder':
                        subfolder_files = self._get_drive_files(file_id)
                        drive_files.update(subfolder_files)
                    else:
                        # Определяем относительный путь файла
                        rel_path = self._get_relative_path(file_id, folder_id)
                        
                        drive_files[file_id] = {
                            'name': file_name,
                            'parent_id': parent_id,
                            'mime_type': mime_type,
                            'modified_time': modified_time,
                            'size': size,
                            'rel_path': rel_path
                        }
                
                page_token = response.get('nextPageToken', None)
                if not page_token:
                    break
            
            return drive_files
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов из Google Drive: {e}")
            return {}
    
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
    
    def _get_relative_path(self, file_id: str, root_folder_id: str) -> str:
        """
        Получение относительного пути файла в Google Drive
        
        Args:
            file_id (str): ID файла
            root_folder_id (str): ID корневой папки
            
        Returns:
            str: Относительный путь файла
        """
        try:
            path_parts = []
            current_id = file_id
            
            while current_id != root_folder_id:
                # Получаем информацию о файле/папке
                file_info = self.service.files().get(
                    fileId=current_id,
                    fields='id, name, parents'
                ).execute()
                
                # Добавляем имя файла/папки в путь
                path_parts.insert(0, file_info.get('name'))
                
                # Переходим к родительской папке
                parents = file_info.get('parents', [])
                if not parents:
                    break
                
                current_id = parents[0]
                
                # Защита от бесконечного цикла
                if len(path_parts) > 20:  # Максимальная глубина вложенности
                    break
            
            return os.path.join(*path_parts)
            
        except Exception as e:
            logger.error(f"Ошибка при получении относительного пути для файла {file_id}: {e}")
            return ""
    
    def _need_upload(self, local_file_path: str, drive_file_id: str, config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли загружать/обновлять файл
        
        Args:
            local_file_path (str): Путь к локальному файлу
            drive_file_id (str): ID файла в Google Drive
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
            
            # Получаем информацию о файле в Google Drive
            drive_file_info = self.service.files().get(
                fileId=drive_file_id,
                fields='id, name, modifiedTime, size'
            ).execute()
            
            drive_size = int(drive_file_info.get('size', 0))
            drive_modified_time = drive_file_info.get('modifiedTime')
            
            # Преобразуем время модификации из Google Drive в timestamp
            if drive_modified_time:
                drive_mtime = TimeUtils.parse_iso8601(drive_modified_time)
            else:
                drive_mtime = 0
            
            # Сравниваем размеры
            if local_size != drive_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime > drive_mtime:
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
    
    def _need_download(self, drive_file_id: str, local_file_path: str, config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли скачивать/обновлять файл
        
        Args:
            drive_file_id (str): ID файла в Google Drive
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
            
            # Получаем информацию о файле в Google Drive
            drive_file_info = self.service.files().get(
                fileId=drive_file_id,
                fields='id, name, modifiedTime, size'
            ).execute()
            
            drive_size = int(drive_file_info.get('size', 0))
            drive_modified_time = drive_file_info.get('modifiedTime')
            
            # Преобразуем время модификации из Google Drive в timestamp
            if drive_modified_time:
                drive_mtime = TimeUtils.parse_iso8601(drive_modified_time)
            else:
                drive_mtime = 0
            
            # Сравниваем размеры
            if local_size != drive_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime < drive_mtime:
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
    
    def _upload_file(self, local_file_path: str, drive_file_name: str, parent_id: str, 
                    file_id: Optional[str] = None, 
                    callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Загрузка/обновление файла в Google Drive
        
        Args:
            local_file_path (str): Путь к локальному файлу
            drive_file_name (str): Имя файла в Google Drive
            parent_id (str): ID родительской папки в Google Drive
            file_id (Optional[str]): ID файла для обновления (None для новой загрузки)
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если загрузка успешна
        """
        try:
            media = MediaFileUpload(local_file_path, resumable=True)
            
            if file_id:
                # Обновляем существующий файл
                file_metadata = {'name': drive_file_name}
                file = self.service.files().update(
                    fileId=file_id,
                    body=file_metadata,
                    media_body=media
                ).execute()
                
                info_msg = f"Обновлен файл в Google Drive: {drive_file_name}"
                logger.info(info_msg)
                if callback:
                    callback(info_msg, "info")
            else:
                # Загружаем новый файл
                file_metadata = {
                    'name': drive_file_name,
                    'parents': [parent_id]
                }
                
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                
                info_msg = f"Загружен файл в Google Drive: {drive_file_name}"
                logger.info(info_msg)
                if callback:
                    callback(info_msg, "info")
            
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при загрузке файла {local_file_path} в Google Drive: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _download_file(self, file_id: str, local_file_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Скачивание файла из Google Drive
        
        Args:
            file_id (str): ID файла в Google Drive
            local_file_path (str): Путь для сохранения файла
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если скачивание успешно
        """
        try:
            # Получаем информацию о файле
            file_info = self.service.files().get(
                fileId=file_id,
                fields='id, name, mimeType'
            ).execute()
            
            file_name = file_info.get('name', 'Unknown')
            mime_type = file_info.get('mimeType')
            
            # Создаем директорию для сохранения файла, если она не существует
            output_dir = os.path.dirname(local_file_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Если это Google Docs, Sheets и т.д., экспортируем в соответствующий формат
            if mime_type == 'application/vnd.google-apps.document':
                request = self.service.files().export_media(fileId=file_id, mimeType='application/pdf')
                local_file_path += '.pdf'
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                request = self.service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                local_file_path += '.xlsx'
            elif mime_type == 'application/vnd.google-apps.presentation':
                request = self.service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.presentationml.presentation')
                local_file_path += '.pptx'
            else:
                # Для обычных файлов просто скачиваем
                request = self.service.files().get_media(fileId=file_id)
            
            # Скачиваем файл
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            
            while not done:
                status, done = downloader.next_chunk()
            
            # Сохраняем файл на диск
            with open(local_file_path, 'wb') as f:
                f.write(fh.getvalue())
            
            info_msg = f"Скачан файл из Google Drive: {file_name}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при скачивании файла {file_id} из Google Drive: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _delete_file(self, file_id: str, callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Удаление файла из Google Drive
        
        Args:
            file_id (str): ID файла в Google Drive
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если удаление успешно
        """
        try:
            # Получаем информацию о файле перед удалением
            file_info = self.service.files().get(
                fileId=file_id,
                fields='id, name'
            ).execute()
            
            file_name = file_info.get('name', 'Unknown')
            
            # Удаляем файл
            self.service.files().delete(fileId=file_id).execute()
            
            info_msg = f"Удален файл из Google Drive: {file_name} (ID: {file_id})"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при удалении файла {file_id} из Google Drive: {e}"
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
                file_hash=None,  # Для Google Drive не используем хеш
                modified_time=file_stat.st_mtime,
                sync_status=sync_status
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении состояния файла в базе данных: {e}")
    
    def update_file_states(self, config_id: int, source_path: str, target_folder_id: str, direction: str = 'upload'):
        """
        Обновление состояний файлов в базе данных
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_folder_id (str): ID папки в Google Drive
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
                # Обновляем состояния на основе файлов в Google Drive
                drive_files = self._get_drive_files(target_folder_id)
                
                for file_id, file_info in drive_files.items():
                    rel_path = file_info['rel_path']
                    local_file_path = os.path.join(source_path, rel_path)
                    
                    if os.path.exists(local_file_path):
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                
                # Удаляем из базы данных записи о файлах, которых больше нет в Google Drive
                file_states = self.db_manager.get_file_states(config_id)
                for state in file_states:
                    if state['file_path'] not in {info['rel_path'] for info in drive_files.values()}:
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
        summary.append("Статистика синхронизации с Google Drive:")
        summary.append(f"  Загружено: {self.sync_stats['uploaded']}")
        summary.append(f"  Обновлено: {self.sync_stats['updated']}")
        summary.append(f"  Скачано: {self.sync_stats['downloaded']}")
        summary.append(f"  Удалено: {self.sync_stats['deleted']}")
        summary.append(f"  Пропущено: {self.sync_stats['skipped']}")
        summary.append(f"  Ошибок: {self.sync_stats['errors']}")
        
        return "\n".join(summary)
    
    def preview_sync(self, config_id: int, source_path: str, target_folder_id: str, 
                    direction: str = 'upload') -> Dict[str, Any]:
        """
        Предварительный просмотр синхронизации без выполнения операций
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_folder_id (str): ID папки в Google Drive
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
                # Предпросмотр загрузки в Google Drive
                if not os.path.exists(source_path):
                    preview['errors'].append(f"Исходная папка не существует: {source_path}")
                    return preview
                
                # Получаем списки файлов
                local_files = self._get_local_files(source_path)
                drive_files = self._get_drive_files(target_folder_id)
                
                # Файлы для загрузки
                for rel_path, file_info in local_files.items():
                    # Ищем файл в Google Drive
                    file_id = None
                    for fid, drive_file_info in drive_files.items():
                        if drive_file_info['name'] == os.path.basename(rel_path):
                            file_id = fid
                            break
                    
                    if not file_id:
                        # Файла нет в Google Drive, загружаем
                        preview['to_upload'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
                    else:
                        # Файл есть в Google Drive, проверяем, нужно ли обновлять
                        if self._need_upload(os.path.join(source_path, rel_path), file_id, config_id, rel_path):
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
                for file_id, file_info in drive_files.items():
                    rel_path = file_info['rel_path']
                    local_file_path = os.path.join(source_path, rel_path)
                    
                    if not os.path.exists(local_file_path):
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': int(file_info['size'] or 0),
                            'mtime': TimeUtils.parse_iso8601(file_info['modified_time']) if file_info['modified_time'] else 0
                        })
            
            elif direction == 'download':
                # Предпросмотр скачивания из Google Drive
                # Получаем списки файлов
                local_files = self._get_local_files(source_path) if os.path.exists(source_path) else {}
                drive_files = self._get_drive_files(target_folder_id)
                
                # Файлы для скачивания
                for file_id, file_info in drive_files.items():
                    rel_path = file_info['rel_path']
                    
                    if rel_path not in local_files:
                        # Файла нет локально, скачиваем
                        preview['to_download'].append({
                            'path': rel_path,
                            'size': int(file_info['size'] or 0),
                            'mtime': TimeUtils.parse_iso8601(file_info['modified_time']) if file_info['modified_time'] else 0
                        })
                    else:
                        # Файл есть локально, проверяем, нужно ли обновлять
                        local_file_path = os.path.join(source_path, rel_path)
                        if self._need_download(file_id, local_file_path, config_id, rel_path):
                            preview['to_download'].append({
                                'path': rel_path,
                                'size': int(file_info['size'] or 0),
                                'mtime': TimeUtils.parse_iso8601(file_info['modified_time']) if file_info['modified_time'] else 0
                            })
                        else:
                            preview['to_skip'].append({
                                'path': rel_path,
                                'size': local_files[rel_path]['size'],
                                'mtime': local_files[rel_path]['mtime']
                            })
                
                # Файлы для удаления
                for rel_path in local_files:
                    if rel_path not in {info['rel_path'] for info in drive_files.values()}:
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': local_files[rel_path]['size'],
                            'mtime': local_files[rel_path]['mtime']
                        })
            
            return preview
            
        except Exception as e:
            preview['errors'].append(f"Ошибка при предварительном просмотре синхронизации: {e}")
            return preview

GoogleDriveSync = GoogleDriveSyncManager
