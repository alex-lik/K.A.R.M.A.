import os
import hashlib
import time
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

from src.sync.utils import FileUtils, TimeUtils, CryptoUtils, NetworkUtils

logger = logging.getLogger(__name__)

class S3SyncManager:
    """Менеджер синхронизации с S3-совместимыми хранилищами (R2, S3 и др.)"""
    
    def __init__(self, db_manager, error_handler=None):
        """
        Инициализация менеджера синхронизации с S3-совместимым хранилищем
        
        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.s3_client = None
        self.s3_resource = None
        self.sync_stats = {
            'uploaded': 0,
            'updated': 0,
            'downloaded': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }
        self.current_sync_id = None
    
    def connect(self, access_key: str, secret_key: str, endpoint_url: Optional[str] = None, 
               region_name: str = 'us-east-1', use_ssl: bool = True) -> bool:
        """
        Подключение к S3-совместимому хранилищу
        
        Args:
            access_key (str): Ключ доступа
            secret_key (str): Секретный ключ
            endpoint_url (Optional[str]): URL конечной точки (для не-AWS S3, например Cloudflare R2)
            region_name (str): Регион (по умолчанию us-east-1)
            use_ssl (bool): Использовать ли SSL
            
        Returns:
            bool: True, если подключение успешно
        """
        if not S3_AVAILABLE:
            logger.error("Модуль boto3 не установлен. Установите boto3")
            return False
        
        try:
            # Создаем клиент и ресурс S3
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region_name
            )
            
            # Если указан endpoint_url, используем его (для не-AWS S3)
            if endpoint_url:
                # Убедимся, что URL не содержит протокола, если он указан
                if not endpoint_url.startswith(('http://', 'https://')):
                    endpoint_url = f"https://{endpoint_url}" if use_ssl else f"http://{endpoint_url}"
                
                self.s3_client = session.client('s3', endpoint_url=endpoint_url, use_ssl=use_ssl)
                self.s3_resource = session.resource('s3', endpoint_url=endpoint_url, use_ssl=use_ssl)
            else:
                self.s3_client = session.client('s3', use_ssl=use_ssl)
                self.s3_resource = session.resource('s3', use_ssl=use_ssl)
            
            # Проверяем подключение, пытаясь получить список бакетов
            self.s3_client.list_buckets()
            
            logger.info(f"Подключение к S3-хранилищу выполнено успешно")
            if endpoint_url:
                logger.info(f"Используется конечная точка: {endpoint_url}")
            
            return True
            
        except (NoCredentialsError, ClientError) as e:
            logger.error(f"Ошибка при подключении к S3-хранилищу: {e}")
            return False
    
    def disconnect(self):
        """Отключение от S3-хранилища"""
        # Для S3 не нужно явное отключение
        self.s3_client = None
        self.s3_resource = None
        logger.info("Отключение от S3-хранилища выполнено успешно")
    
    def list_buckets(self) -> List[str]:
        """
        Получение списка доступных бакетов
        
        Returns:
            List[str]: Список имен бакетов
        """
        if not self.s3_client:
            logger.error("S3-соединение не установлено")
            return []
        
        try:
            response = self.s3_client.list_buckets()
            buckets = [bucket['Name'] for bucket in response['Buckets']]
            return buckets
        except ClientError as e:
            logger.error(f"Ошибка при получении списка бакетов: {e}")
            return []
    
    def ensure_bucket(self, bucket_name: str) -> bool:
        """
        Проверка существования бакета и его создание при необходимости
        
        Args:
            bucket_name (str): Имя бакета
            
        Returns:
            bool: True, если бакет существует или создан
        """
        if not self.s3_client:
            logger.error("S3-соединение не установлено")
            return False
        
        try:
            # Проверяем, существует ли бакет
            self.s3_client.head_bucket(Bucket=bucket_name)
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Бакет не существует, пытаемся создать
                try:
                    # Для некоторых S3-совместимых хранилищ (например, Cloudflare R2) 
                    # может потребоваться указать регион при создании бакета
                    self.s3_client.create_bucket(Bucket=bucket_name)
                    logger.info(f"Создан бакет: {bucket_name}")
                    return True
                except ClientError as create_error:
                    logger.error(f"Ошибка при создании бакета {bucket_name}: {create_error}")
                    return False
            else:
                logger.error(f"Ошибка при проверке существования бакета {bucket_name}: {e}")
                return False
    
    def sync_folders(self, config_id: int, source_path: str, target_info: Dict[str, str], 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    direction: str = 'upload', delete_mode: bool = True) -> Dict[str, int]:
        """
        Синхронизация папок с S3-хранилищем
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_info (Dict[str, str]): Информация о целевом S3-ресурсе {bucket_name, prefix}
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            direction (str): Направление синхронизации ('upload' или 'download')
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
            
        Returns:
            Dict[str, int]: Статистика синхронизации
        """
        if not self.s3_client:
            error_msg = "S3-соединение не установлено"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            return self.sync_stats
        
        bucket_name = target_info.get('bucket_name', '')
        prefix = target_info.get('prefix', '')
        
        if not bucket_name:
            error_msg = "Не указано имя бакета S3-хранилища"
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
            message=f"Начало синхронизации с S3-хранилищем: {source_path} <-> {bucket_name}/{prefix}"
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
                # Синхронизация из локальной папки в S3
                self._sync_upload(config_id, source_path, bucket_name, prefix, callback, delete_mode)
            elif direction == 'download':
                # Синхронизация из S3 в локальную папку
                self._sync_download(config_id, source_path, bucket_name, prefix, callback, delete_mode)
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
                
                message = f"Синхронизация с S3-хранилищем завершена. " \
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
            error_msg = f"Ошибка при синхронизации с S3-хранилищем: {e}"
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
    
    def _sync_upload(self, config_id: int, source_path: str, bucket_name: str, prefix: str, 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    delete_mode: bool = True):
        """
        Синхронизация из локальной папки в S3
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            bucket_name (str): Имя бакета S3
            prefix (str): Префикс в бакете S3
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
        """
        # Проверяем существование бакета
        if not self.ensure_bucket(bucket_name):
            error_msg = f"Не удалось проверить/создать бакет: {bucket_name}"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            self.sync_stats['errors'] += 1
            return
        
        # Получаем список объектов в S3
        s3_objects = self._get_s3_objects(bucket_name, prefix)
        
        # Синхронизируем файлы из локальной папки в S3
        for root, dirs, files in os.walk(source_path):
            # Пропускаем скрытые папки
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                # Пропускаем скрытые файлы
                if filename.startswith('.'):
                    continue
                    
                local_file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(local_file_path, source_path)
                
                # Определяем ключ объекта в S3
                s3_key = os.path.join(prefix, rel_path).replace("\\", "/")
                
                # Проверяем, существует ли объект в S3
                object_exists = False
                object_mtime = None
                object_size = None
                object_etag = None
                
                for obj in s3_objects:
                    if obj['key'] == s3_key:
                        object_exists = True
                        object_mtime = obj['last_modified'].timestamp()
                        object_size = obj['size']
                        object_etag = obj['etag'].strip('"')
                        break
                
                if object_exists:
                    # Объект существует в S3, проверяем, нужно ли обновлять
                    if self._need_upload(local_file_path, object_mtime, object_size, object_etag, config_id, rel_path):
                        if self._upload_file(local_file_path, bucket_name, s3_key, callback):
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
                    # Объекта нет в S3, загружаем
                    if self._upload_file(local_file_path, bucket_name, s3_key, callback):
                        self.sync_stats['uploaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
        
        # Удаляем объекты, которые есть в S3, но отсутствуют локально
        if delete_mode:
            for obj in s3_objects:
                s3_key = obj['key']
                
                # Пропускаем объекты, которые не соответствуют префиксу
                if prefix and not s3_key.startswith(prefix):
                    continue
                
                # Определяем относительный путь
                if prefix:
                    rel_path = s3_key[len(prefix):].lstrip('/')
                else:
                    rel_path = s3_key
                
                local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))
                
                if not os.path.exists(local_file_path):
                    if self._delete_object(bucket_name, s3_key, callback):
                        self.sync_stats['deleted'] += 1
                        
                        # Удаляем состояние файла из базы данных
                        self.db_manager.delete_file_state(config_id, rel_path)
    
    def _sync_download(self, config_id: int, target_path: str, bucket_name: str, prefix: str, 
                      callback: Optional[Callable[[str, str], None]] = None, 
                      delete_mode: bool = True):
        """
        Синхронизация из S3 в локальную папку
        
        Args:
            config_id (int): ID конфигурации в базе данных
            target_path (str): Путь к локальной папке
            bucket_name (str): Имя бакета S3
            prefix (str): Префикс в бакете S3
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
        
        # Проверяем существование бакета
        if not self.ensure_bucket(bucket_name):
            error_msg = f"Не удалось проверить/создать бакет: {bucket_name}"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            self.sync_stats['errors'] += 1
            return
        
        # Получаем список объектов в S3
        s3_objects = self._get_s3_objects(bucket_name, prefix)
        
        # Получаем список локальных файлов
        local_files = self._get_local_files(target_path)
        
        # Синхронизируем файлы из S3 в локальную папку
        for obj in s3_objects:
            s3_key = obj['key']
            
            # Пропускаем объекты, которые не соответствуют префиксу
            if prefix and not s3_key.startswith(prefix):
                continue
            
            # Определяем относительный путь
            if prefix:
                rel_path = s3_key[len(prefix):].lstrip('/')
            else:
                rel_path = s3_key
            
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
                if self._download_file(bucket_name, s3_key, local_file_path, callback):
                    self.sync_stats['downloaded'] += 1
                    
                    # Обновляем состояние файла в базе данных
                    self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
            else:
                # Файл есть локально, проверяем, нужно ли обновлять
                if self._need_download(bucket_name, s3_key, local_file_path, config_id, rel_path):
                    if self._download_file(bucket_name, s3_key, local_file_path, callback):
                        self.sync_stats['downloaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                else:
                    self.sync_stats['skipped'] += 1
                    debug_msg = f"Файл пропущен (без изменений): {rel_path}"
                    logger.debug(debug_msg)
                    if callback:
                        callback(debug_msg, "debug")
        
        # Удаляем файлы, которые есть локально, но отсутствуют в S3
        if delete_mode:
            for rel_path in local_files:
                s3_key = os.path.join(prefix, rel_path).replace("\\", "/")
                
                # Проверяем, существует ли объект в S3
                object_exists = False
                for obj in s3_objects:
                    if obj['key'] == s3_key:
                        object_exists = True
                        break
                
                if not object_exists:
                    local_file_path = os.path.join(target_path, rel_path)
                    if self._delete_local_file(local_file_path, callback):
                        self.sync_stats['deleted'] += 1
                        
                        # Удаляем состояние файла из базы данных
                        self.db_manager.delete_file_state(config_id, rel_path)
    
    def _get_s3_objects(self, bucket_name: str, prefix: str = '') -> List[Dict[str, Any]]:
        """
        Получение списка объектов в S3-бакете
        
        Args:
            bucket_name (str): Имя бакета
            prefix (str): Префикс для фильтрации объектов
            
        Returns:
            List[Dict[str, Any]]: Список словарей с информацией об объектах
        """
        objects = []
        
        try:
            # Создаем пагинатор для обработки большого количества объектов
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            # Формируем параметры запроса
            params = {'Bucket': bucket_name}
            if prefix:
                params['Prefix'] = prefix
            
            # Получаем все страницы с объектами
            for page in paginator.paginate(**params):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'],
                            'etag': obj['ETag']
                        })
            
            return objects
            
        except ClientError as e:
            logger.error(f"Ошибка при получении списка объектов из S3: {e}")
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
                    remote_size: Optional[int], remote_etag: Optional[str], 
                    config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли загружать/обновлять объект
        
        Args:
            local_file_path (str): Путь к локальному файлу
            remote_mtime (Optional[float]): Время модификации объекта в S3
            remote_size (Optional[int]): Размер объекта в S3
            remote_etag (Optional[str]): ETag объекта в S3
            config_id (int): ID конфигурации в базе данных
            rel_path (str): Относительный путь к файлу
            
        Returns:
            bool: True, если объект нужно загрузить/обновить
        """
        try:
            # Получаем информацию о локальном файле
            local_stat = os.stat(local_file_path)
            local_size = local_stat.st_size
            local_mtime = local_stat.st_mtime
            
            # Если удаленный объект не существует, загружаем
            if remote_mtime is None or remote_size is None or remote_etag is None:
                return True
            
            # Сравниваем размеры
            if local_size != remote_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime > remote_mtime:
                return True
            
            # Сравниваем ETag (хеш) объекта
            local_etag = self.calculate_file_etag(local_file_path)
            if local_etag != remote_etag:
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
            return True  # В случае ошибки, считаем что объект нужно обновить
    
    def _need_download(self, bucket_name: str, s3_key: str, local_file_path: str, 
                      config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли скачивать/обновлять файл
        
        Args:
            bucket_name (str): Имя бакета S3
            s3_key (str): Ключ объекта в S3
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
            
            # Получаем информацию об объекте в S3
            try:
                response = self.s3_client.head_object(Bucket=bucket_name, Key=s3_key)
                remote_size = response['ContentLength']
                remote_mtime = response['LastModified'].timestamp()
                remote_etag = response['ETag'].strip('"')
            except ClientError:
                # Объект не найден в S3
                return False
            
            # Сравниваем размеры
            if local_size != remote_size:
                return True
            
            # Сравниваем время модификации
            if local_mtime < remote_mtime:
                return True
            
            # Сравниваем ETag (хеш) объекта
            local_etag = self.calculate_file_etag(local_file_path)
            if local_etag != remote_etag:
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
    
    def calculate_file_etag(self, file_path: str, chunk_size: int = 8 * 1024 * 1024) -> Optional[str]:
        """
        Вычисление ETag файла для сравнения с объектом в S3
        
        Args:
            file_path (str): Путь к файлу
            chunk_size (int): Размер чанка для вычисления MD5
            
        Returns:
            Optional[str]: ETag файла или None в случае ошибки
        """
        md5s = []
        
        try:
            with open(file_path, 'rb') as f:
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    md5s.append(hashlib.md5(data).digest())
            
            if len(md5s) == 1:
                # Для одного чанка ETag - это просто MD5
                return hashlib.md5(md5s[0]).hexdigest()
            else:
                # Для нескольких чанков ETag вычисляется как MD5 от конкатенации MD5 каждого чанка
                digests = b''.join(md5s)
                return '{}-{}'.format(hashlib.md5(digests).hexdigest(), len(md5s))
                
        except Exception as e:
            logger.error(f"Ошибка при вычислении ETag файла {file_path}: {e}")
            return None
    
    def _upload_file(self, local_file_path: str, bucket_name: str, s3_key: str, 
                    callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Загрузка файла в S3
        
        Args:
            local_file_path (str): Путь к локальному файлу
            bucket_name (str): Имя бакета
            s3_key (str): Ключ объекта в S3
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если загрузка успешна
        """
        try:
            # Определяем Content-Type на основе расширения файла
            content_type = self._get_content_type(local_file_path)
            
            # Загружаем файл
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            self.s3_client.upload_file(
                local_file_path, 
                bucket_name, 
                s3_key,
                ExtraArgs=extra_args
            )
            
            info_msg = f"Загружен файл в S3: {os.path.basename(local_file_path)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
                
        except ClientError as e:
            error_msg = f"Ошибка при загрузке файла {local_file_path} в S3: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _download_file(self, bucket_name: str, s3_key: str, local_file_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Скачивание файла из S3
        
        Args:
            bucket_name (str): Имя бакета
            s3_key (str): Ключ объекта в S3
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
            self.s3_client.download_file(bucket_name, s3_key, local_file_path)
            
            info_msg = f"Скачан файл из S3: {os.path.basename(s3_key)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except ClientError as e:
            error_msg = f"Ошибка при скачивании файла {s3_key} из S3: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _delete_object(self, bucket_name: str, s3_key: str, 
                      callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Удаление объекта из S3
        
        Args:
            bucket_name (str): Имя бакета
            s3_key (str): Ключ объекта в S3
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если удаление успешно
        """
        try:
            # Удаляем объект
            self.s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
            
            info_msg = f"Удален объект из S3: {os.path.basename(s3_key)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except ClientError as e:
            error_msg = f"Ошибка при удалении объекта {s3_key} из S3: {e}"
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
    
    def _get_content_type(self, file_path: str) -> Optional[str]:
        """
        Определение Content-Type на основе расширения файла
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            Optional[str]: Content-Type или None, если не удалось определить
        """
        import mimetypes
        
        # Регистрируем дополнительные типы, если необходимо
        mimetypes.add_type('application/json', '.json')
        mimetypes.add_type('application/xml', '.xml')
        
        content_type, _ = mimetypes.guess_type(file_path)
        return content_type
    
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
                file_hash=None,  # Для S3 не используем хеш
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
            target_info (Dict[str, str]): Информация о целевом S3-ресурсе {bucket_name, prefix}
            direction (str): Направление синхронизации ('upload' или 'download')
        """
        try:
            bucket_name = target_info.get('bucket_name', '')
            prefix = target_info.get('prefix', '')
            
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
                # Обновляем состояния на основе файлов в S3
                s3_objects = self._get_s3_objects(bucket_name, prefix)
                
                for obj in s3_objects:
                    s3_key = obj['key']
                    
                    # Пропускаем объекты, которые не соответствуют префиксу
                    if prefix and not s3_key.startswith(prefix):
                        continue
                    
                    # Определяем относительный путь
                    if prefix:
                        rel_path = s3_key[len(prefix):].lstrip('/')
                    else:
                        rel_path = s3_key
                    
                    local_file_path = os.path.join(source_path, rel_path)
                    
                    if os.path.exists(local_file_path):
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                
                # Удаляем из базы данных записи о файлах, которых больше нет в S3
                file_states = self.db_manager.get_file_states(config_id)
                for state in file_states:
                    s3_key = os.path.join(prefix, state['file_path']).replace("\\", "/")
                    
                    # Проверяем, существует ли объект в S3
                    object_exists = False
                    for obj in s3_objects:
                        if obj['key'] == s3_key:
                            object_exists = True
                            break
                    
                    if not object_exists:
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
        summary.append("Статистика синхронизации с S3-хранилищем:")
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
            target_info (Dict[str, str]): Информация о целевом S3-ресурсе {bucket_name, prefix}
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
            bucket_name = target_info.get('bucket_name', '')
            prefix = target_info.get('prefix', '')
            
            if direction == 'upload':
                # Предпросмотр загрузки в S3
                if not os.path.exists(source_path):
                    preview['errors'].append(f"Исходная папка не существует: {source_path}")
                    return preview
                
                # Получаем списки файлов
                local_files = self._get_local_files(source_path)
                s3_objects = self._get_s3_objects(bucket_name, prefix)
                
                # Файлы для загрузки
                for rel_path, file_info in local_files.items():
                    # Ищем файл в S3
                    s3_key = os.path.join(prefix, rel_path).replace("\\", "/")
                    remote_mtime = None
                    remote_size = None
                    remote_etag = None
                    
                    for obj in s3_objects:
                        if obj['key'] == s3_key:
                            remote_mtime = obj['last_modified'].timestamp()
                            remote_size = obj['size']
                            remote_etag = obj['etag'].strip('"')
                            break
                    
                    if remote_mtime is None or remote_size is None or remote_etag is None:
                        # Файла нет в S3, загружаем
                        preview['to_upload'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
                    else:
                        # Файл есть в S3, проверяем, нужно ли обновлять
                        if self._need_upload(os.path.join(source_path, rel_path), remote_mtime, remote_size, remote_etag, config_id, rel_path):
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
                for obj in s3_objects:
                    s3_key = obj['key']
                    
                    # Пропускаем объекты, которые не соответствуют префиксу
                    if prefix and not s3_key.startswith(prefix):
                        continue
                    
                    # Определяем относительный путь
                    if prefix:
                        rel_path = s3_key[len(prefix):].lstrip('/')
                    else:
                        rel_path = s3_key
                    
                    local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))
                    
                    if not os.path.exists(local_file_path):
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': obj['size'],
                            'mtime': obj['last_modified'].timestamp()
                        })
            
            elif direction == 'download':
                # Предпросмотр скачивания из S3
                # Получаем списки файлов
                local_files = self._get_local_files(source_path) if os.path.exists(source_path) else {}
                s3_objects = self._get_s3_objects(bucket_name, prefix)
                
                # Файлы для скачивания
                for obj in s3_objects:
                    s3_key = obj['key']
                    
                    # Пропускаем объекты, которые не соответствуют префиксу
                    if prefix and not s3_key.startswith(prefix):
                        continue
                    
                    # Определяем относительный путь
                    if prefix:
                        rel_path = s3_key[len(prefix):].lstrip('/')
                    else:
                        rel_path = s3_key
                    
                    if rel_path not in local_files:
                        # Файла нет локально, скачиваем
                        preview['to_download'].append({
                            'path': rel_path,
                            'size': obj['size'],
                            'mtime': obj['last_modified'].timestamp()
                        })
                    else:
                        # Файл есть локально, проверяем, нужно ли обновлять
                        local_file_path = os.path.join(source_path, rel_path)
                        if self._need_download(bucket_name, s3_key, local_file_path, config_id, rel_path):
                            preview['to_download'].append({
                                'path': rel_path,
                                'size': obj['size'],
                                'mtime': obj['last_modified'].timestamp()
                            })
                        else:
                            preview['to_skip'].append({
                                'path': rel_path,
                                'size': local_files[rel_path]['size'],
                                'mtime': local_files[rel_path]['mtime']
                            })
                
                # Файлы для удаления
                for rel_path in local_files:
                    s3_key = os.path.join(prefix, rel_path).replace("\\", "/")
                    
                    # Проверяем, существует ли объект в S3
                    object_exists = False
                    for obj in s3_objects:
                        if obj['key'] == s3_key:
                            object_exists = True
                            break
                    
                    if not object_exists:
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': local_files[rel_path]['size'],
                            'mtime': local_files[rel_path]['mtime']
                        })
            
            return preview
            
        except Exception as e:
            preview['errors'].append(f"Ошибка при предварительном просмотре синхронизации: {e}")
            return preview

S3Sync = S3SyncManager
