import os
import hashlib
import time
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

try:
    from smb.SMBConnection import SMBConnection
    from smb.base import SharedFile
    SMB_AVAILABLE = True
except ImportError:
    SMB_AVAILABLE = False

from src.sync.utils import FileUtils, TimeUtils, CryptoUtils, NetworkUtils

logger = logging.getLogger(__name__)

class SMBSyncManager:
    """Менеджер синхронизации с SMB-ресурсом"""
    
    def __init__(self, db_manager, error_handler=None):
        """
        Инициализация менеджера синхронизации с SMB-ресурсом
        
        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.conn = None
        self.sync_stats = {
            'copied': 0,
            'updated': 0,
            'downloaded': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }
        self.current_sync_id = None
    
    def connect(self, server: str, username: str, password: str, 
               domain: str = '', port: int = 139, timeout: int = 30, 
               use_ntlm_v2: bool = True) -> bool:
        """
        Подключение к SMB-ресурсу
        
        Args:
            server (str): Имя или IP-адрес сервера
            username (str): Имя пользователя
            password (str): Пароль
            domain (str): Домен (по умолчанию пустой)
            port (int): Порт SMB-сервера (по умолчанию 139)
            timeout (int): Таймаут подключения в секундах
            use_ntlm_v2 (bool): Использовать ли NTLMv2 аутентификацию
            
        Returns:
            bool: True, если подключение успешно
        """
        if not SMB_AVAILABLE:
            logger.error("Модуль SMB не установлен. Установите pysmb")
            return False
        
        try:
            # Создаем подключение
            self.conn = SMBConnection(
                username, password, '', server, domain=domain,
                use_ntlm_v2=use_ntlm_v2, is_direct_tcp=True
            )
            
            # Подключаемся к серверу
            self.conn.connect(server, port, timeout=timeout)
            logger.info(f"Подключение к SMB-ресурсу {server} выполнено успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при подключении к SMB-ресурсу {server}: {e}")
            return False
    
    def disconnect(self):
        """Отключение от SMB-ресурса"""
        if self.conn:
            try:
                self.conn.close()
                logger.info("Отключение от SMB-ресурса выполнено успешно")
            except Exception as e:
                logger.error(f"Ошибка при отключении от SMB-ресурса: {e}")
            finally:
                self.conn = None
    
    def list_shares(self) -> List[str]:
        """
        Получение списка доступных шар на SMB-сервере
        
        Returns:
            List[str]: Список имен шар
        """
        if not self.conn:
            logger.error("SMB-соединение не установлено")
            return []
        
        try:
            shares = self.conn.listShares()
            share_names = [share.name for share in shares]
            return share_names
        except Exception as e:
            logger.error(f"Ошибка при получении списка шар: {e}")
            return []
    
    def ensure_directory(self, share_name: str, remote_path: str) -> bool:
        """
        Создание директории на SMB-ресурсе, если она не существует
        
        Args:
            share_name (str): Имя шары
            remote_path (str): Путь к директории на SMB-ресурсе
            
        Returns:
            bool: True, если директория существует или создана
        """
        if not self.conn:
            logger.error("SMB-соединение не установлено")
            return False
        
        try:
            # Разделяем путь на части
            path_parts = remote_path.split('/')
            current_path = ""
            
            for part in path_parts:
                if not part:  # Пропускаем пустые части (например, в начале пути)
                    continue
                    
                current_path += "/" + part if current_path else part
                
                try:
                    # Проверяем, существует ли директория
                    self.conn.getAttributes(share_name, current_path)
                except Exception:
                    # Директория не существует, создаем ее
                    try:
                        self.conn.createDirectory(share_name, current_path)
                        logger.debug(f"Создана директория: {current_path}")
                    except Exception as e:
                        logger.error(f"Ошибка при создании директории {current_path}: {e}")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при создании директории {remote_path}: {e}")
            return False
    
    def sync_folders(self, config_id: int, source_path: str, target_info: Dict[str, str], 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    direction: str = 'upload', delete_mode: bool = True) -> Dict[str, int]:
        """
        Синхронизация папок с SMB-ресурсом
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            target_info (Dict[str, str]): Информация о целевом SMB-ресурсе {share_name, path}
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            direction (str): Направление синхронизации ('upload' или 'download')
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
            
        Returns:
            Dict[str, int]: Статистика синхронизации
        """
        if not self.conn:
            error_msg = "SMB-соединение не установлено"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            return self.sync_stats
        
        share_name = target_info.get('share_name', '')
        target_path = target_info.get('path', '')
        
        if not share_name:
            error_msg = "Не указано имя шары SMB-ресурса"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            return self.sync_stats
        
        # Сброс статистики
        self.sync_stats = {
            'copied': 0,
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
            message=f"Начало синхронизации с SMB-ресурсом: {source_path} <-> {share_name}/{target_path}"
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
                # Синхронизация из локальной папки на SMB-ресурс
                self._sync_upload(config_id, source_path, share_name, target_path, callback, delete_mode)
            elif direction == 'download':
                # Синхронизация с SMB-ресурса в локальную папку
                self._sync_download(config_id, source_path, share_name, target_path, callback, delete_mode)
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
                total_files = self.sync_stats['copied'] + self.sync_stats['updated'] + \
                             self.sync_stats['downloaded'] + self.sync_stats['skipped']
                status = 'success' if self.sync_stats['errors'] == 0 else 'error'
                
                message = f"Синхронизация с SMB-ресурсом завершена. " \
                         f"Скопировано: {self.sync_stats['copied']}, " \
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
            error_msg = f"Ошибка при синхронизации с SMB-ресурсом: {e}"
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
    
    def _sync_upload(self, config_id: int, source_path: str, share_name: str, target_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None, 
                    delete_mode: bool = True):
        """
        Синхронизация из локальной папки на SMB-ресурс
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к локальной папке
            share_name (str): Имя шары SMB-ресурса
            target_path (str): Путь к папке на SMB-ресурсе
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
        """
        # Создаем целевую директорию на SMB-ресурсе, если она не существует
        if target_path and not self.ensure_directory(share_name, target_path):
            error_msg = f"Не удалось создать директорию на SMB-ресурсе: {target_path}"
            logger.error(error_msg)
            if callback:
                callback(f"Ошибка: {error_msg}", "error")
            self.sync_stats['errors'] += 1
            return
        
        # Получаем список файлов на SMB-ресурсе
        smb_files = self._get_smb_files(share_name, target_path)
        
        # Синхронизируем файлы из локальной папки на SMB-ресурс
        for root, dirs, files in os.walk(source_path):
            # Пропускаем скрытые папки
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                # Пропускаем скрытые файлы
                if filename.startswith('.'):
                    continue
                    
                local_file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(local_file_path, source_path)
                
                # Определяем путь на SMB-ресурсе
                smb_path = os.path.join(target_path, rel_path).replace("\\", "/")
                smb_dir = os.path.dirname(smb_path)
                smb_filename = os.path.basename(smb_path)
                
                # Создаем директорию на SMB-ресурсе, если необходимо
                if smb_dir and not self.ensure_directory(share_name, smb_dir):
                    error_msg = f"Не удалось создать директорию на SMB-ресурсе: {smb_dir}"
                    logger.error(error_msg)
                    if callback:
                        callback(error_msg, "error")
                    self.sync_stats['errors'] += 1
                    continue
                
                # Проверяем, существует ли файл на SMB-ресурсе
                file_exists = False
                file_mtime = None
                file_size = None
                
                for file_info in smb_files:
                    if file_info['path'] == smb_path:
                        file_exists = True
                        file_mtime = file_info['mtime']
                        file_size = file_info['size']
                        break
                
                if file_exists:
                    # Файл существует на SMB-ресурсе, проверяем, нужно ли обновлять
                    if self._need_upload(local_file_path, file_mtime, file_size, config_id, rel_path):
                        if self._upload_file(local_file_path, share_name, smb_path, callback):
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
                    # Файла нет на SMB-ресурсе, копируем
                    if self._upload_file(local_file_path, share_name, smb_path, callback):
                        self.sync_stats['copied'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
        
        # Удаляем файлы, которые есть на SMB-ресурсе, но отсутствуют локально
        # ВАЖНО: удаляем только те файлы, которые система сама синхронизировала (есть в file_states)
        if delete_mode:
            # Получаем список файлов, которые были синхронизированы системой
            synced_files = set()
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                synced_files.add(state['file_path'])

            for file_info in smb_files:
                smb_path = file_info['path']
                rel_path = os.path.relpath(smb_path, target_path).replace("\\", "/")
                local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))

                if not os.path.exists(local_file_path):
                    # Удаляем только если этот файл был синхронизирован системой
                    if rel_path in synced_files:
                        if self._delete_file(share_name, smb_path, callback):
                            self.sync_stats['deleted'] += 1

                            # Удаляем состояние файла из базы данных
                            self.db_manager.delete_file_state(config_id, rel_path)
                    else:
                        # Файл не был синхронизирован системой, пропускаем
                        logger.debug(f"Пропущен файл {rel_path} - не был синхронизирован этой системой")
                        if callback:
                            callback(f"Пропущен файл (не синхронизирован системой): {rel_path}", "debug")
    
    def _sync_download(self, config_id: int, target_path: str, share_name: str, source_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None, 
                      delete_mode: bool = True):
        """
        Синхронизация с SMB-ресурса в локальную папку
        
        Args:
            config_id (int): ID конфигурации в базе данных
            target_path (str): Путь к локальной папке
            share_name (str): Имя шары SMB-ресурса
            source_path (str): Путь к папке на SMB-ресурсе
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
        
        # Получаем список файлов на SMB-ресурсе
        smb_files = self._get_smb_files(share_name, source_path)
        
        # Получаем список локальных файлов
        local_files = self._get_local_files(target_path)
        
        # Синхронизируем файлы с SMB-ресурса в локальную папку
        for file_info in smb_files:
            smb_path = file_info['path']
            rel_path = os.path.relpath(smb_path, source_path).replace("\\", "/")
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
                if self._download_file(share_name, smb_path, local_file_path, callback):
                    self.sync_stats['downloaded'] += 1
                    
                    # Обновляем состояние файла в базе данных
                    self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
            else:
                # Файл есть локально, проверяем, нужно ли обновлять
                if self._need_download(share_name, smb_path, local_file_path, config_id, rel_path):
                    if self._download_file(share_name, smb_path, local_file_path, callback):
                        self.sync_stats['downloaded'] += 1
                        
                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                else:
                    self.sync_stats['skipped'] += 1
                    debug_msg = f"Файл пропущен (без изменений): {rel_path}"
                    logger.debug(debug_msg)
                    if callback:
                        callback(debug_msg, "debug")
        
        # Удаляем файлы, которые есть локально, но отсутствуют на SMB-ресурсе
        # ВАЖНО: удаляем только те файлы, которые система сама синхронизировала (есть в file_states)
        if delete_mode:
            # Получаем список файлов, которые были синхронизированы системой
            synced_files = set()
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                synced_files.add(state['file_path'])

            for rel_path in local_files:
                smb_path = os.path.join(source_path, rel_path).replace("\\", "/")

                # Проверяем, существует ли файл на SMB-ресурсе
                file_exists = False
                for file_info in smb_files:
                    if file_info['path'] == smb_path:
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
    
    def _get_smb_files(self, share_name: str, remote_path: str) -> List[Dict[str, Any]]:
        """
        Рекурсивное получение списка файлов с SMB-ресурса
        
        Args:
            share_name (str): Имя шары
            remote_path (str): Путь к папке на SMB-ресурсе
            
        Returns:
            List[Dict[str, Any]]: Список словарей с информацией о файлах
        """
        files = []
        
        try:
            # Получаем список файлов и директорий
            items = self.conn.listPath(share_name, remote_path)
            
            for item in items:
                # Пропускаем специальные директории
                if item.filename in ['.', '..']:
                    continue
                
                # Формируем полный путь
                item_path = f"{remote_path}/{item.filename}" if remote_path != '/' else f"/{item.filename}"
                
                if item.isDirectory:
                    # Рекурсивно получаем содержимое директории
                    sub_files = self._get_smb_files(share_name, item_path)
                    files.extend(sub_files)
                else:
                    files.append({
                        'path': item_path,
                        'name': item.filename,
                        'size': item.file_size,
                        'mtime': item.last_write_time.timestamp()
                    })
            
            return files
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов с SMB-ресурса: {e}")
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
            remote_mtime (Optional[float]): Время модификации файла на SMB-ресурсе
            remote_size (Optional[int]): Размер файла на SMB-ресурсе
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
            logger.error(f"Ошибка при проверке необходимости копирования файла {local_file_path}: {e}")
            return True  # В случае ошибки, считаем что файл нужно обновить
    
    def _need_download(self, share_name: str, remote_path: str, local_file_path: str, 
                      config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли скачивать/обновлять файл
        
        Args:
            share_name (str): Имя шары SMB-ресурса
            remote_path (str): Путь к файлу на SMB-ресурсе
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
            
            # Получаем информацию о файле на SMB-ресурсе
            try:
                remote_file_info = self.conn.getAttributes(share_name, remote_path)
                remote_size = remote_file_info.file_size
                remote_mtime = remote_file_info.last_write_time.timestamp()
            except Exception:
                # Файл не найден на сервере
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
    
    def _upload_file(self, local_file_path: str, share_name: str, remote_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Копирование файла на SMB-ресурс
        
        Args:
            local_file_path (str): Путь к локальному файлу
            share_name (str): Имя шары
            remote_path (str): Путь к файлу на SMB-ресурсе
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если копирование успешно
        """
        try:
            with open(local_file_path, 'rb') as f:
                # Определяем директорию и имя файла на SMB-ресурсе
                remote_dir = os.path.dirname(remote_path)
                remote_filename = os.path.basename(remote_path)
                
                # Копируем файл
                self.conn.storeFile(share_name, remote_path, f)
                
                info_msg = f"Скопирован файл на SMB-ресурс: {os.path.basename(local_file_path)}"
                logger.info(info_msg)
                if callback:
                    callback(info_msg, "info")
                
                return True
                
        except Exception as e:
            error_msg = f"Ошибка при копировании файла {local_file_path} на SMB-ресурс: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _download_file(self, share_name: str, remote_path: str, local_file_path: str, 
                      callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Скачивание файла с SMB-ресурса
        
        Args:
            share_name (str): Имя шары SMB-ресурса
            remote_path (str): Путь к файлу на SMB-ресурсе
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
            with open(local_file_path, 'wb') as f:
                self.conn.retrieveFile(share_name, remote_path, f)
            
            info_msg = f"Скачан файл с SMB-ресурса: {os.path.basename(remote_path)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при скачивании файла {remote_path} с SMB-ресурса: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _delete_file(self, share_name: str, remote_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Удаление файла с SMB-ресурса
        
        Args:
            share_name (str): Имя шары
            remote_path (str): Путь к файлу на SMB-ресурсе
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если удаление успешно
        """
        try:
            # Удаляем файл
            self.conn.deleteFile(share_name, remote_path)
            
            info_msg = f"Удален файл с SMB-ресурса: {os.path.basename(remote_path)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при удалении файла {remote_path} с SMB-ресурса: {e}"
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
                file_hash=None,  # Для SMB не используем хеш
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
            target_info (Dict[str, str]): Информация о целевом SMB-ресурсе {share_name, path}
            direction (str): Направление синхронизации ('upload' или 'download')
        """
        try:
            share_name = target_info.get('share_name', '')
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
                # Обновляем состояния на основе файлов на SMB-ресурсе
                smb_files = self._get_smb_files(share_name, target_path)
                
                for file_info in smb_files:
                    smb_path = file_info['path']
                    rel_path = os.path.relpath(smb_path, target_path).replace("\\", "/")
                    local_file_path = os.path.join(source_path, rel_path)
                    
                    if os.path.exists(local_file_path):
                        self._update_file_state_in_db(config_id, rel_path, local_file_path, 'synced')
                
                # Удаляем из базы данных записи о файлах, которых больше нет на SMB-ресурсе
                file_states = self.db_manager.get_file_states(config_id)
                for state in file_states:
                    smb_path = os.path.join(target_path, state['file_path']).replace("\\", "/")
                    
                    # Проверяем, существует ли файл на SMB-ресурсе
                    file_exists = False
                    for file_info in smb_files:
                        if file_info['path'] == smb_path:
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
        summary.append("Статистика синхронизации с SMB-ресурсом:")
        summary.append(f"  Скопировано: {self.sync_stats['copied']}")
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
            target_info (Dict[str, str]): Информация о целевом SMB-ресурсе {share_name, path}
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
            share_name = target_info.get('share_name', '')
            target_path = target_info.get('path', '')
            
            if direction == 'upload':
                # Предпросмотр загрузки на SMB-ресурс
                if not os.path.exists(source_path):
                    preview['errors'].append(f"Исходная папка не существует: {source_path}")
                    return preview
                
                # Получаем списки файлов
                local_files = self._get_local_files(source_path)
                smb_files = self._get_smb_files(share_name, target_path)
                
                # Файлы для загрузки
                for rel_path, file_info in local_files.items():
                    # Ищем файл на SMB-ресурсе
                    smb_path = os.path.join(target_path, rel_path).replace("\\", "/")
                    remote_mtime = None
                    remote_size = None
                    
                    for smb_file in smb_files:
                        if smb_file['path'] == smb_path:
                            remote_mtime = smb_file['mtime']
                            remote_size = smb_file['size']
                            break
                    
                    if remote_mtime is None or remote_size is None:
                        # Файла нет на SMB-ресурсе, загружаем
                        preview['to_upload'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
                    else:
                        # Файл есть на SMB-ресурсе, проверяем, нужно ли обновлять
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
                for file_info in smb_files:
                    smb_path = file_info['path']
                    rel_path = os.path.relpath(smb_path, target_path).replace("\\", "/")
                    local_file_path = os.path.join(source_path, rel_path.replace("/", os.sep))
                    
                    if not os.path.exists(local_file_path):
                        preview['to_delete'].append({
                            'path': rel_path,
                            'size': file_info['size'],
                            'mtime': file_info['mtime']
                        })
            
            elif direction == 'download':
                # Предпросмотр скачивания с SMB-ресурса
                # Получаем списки файлов
                local_files = self._get_local_files(source_path) if os.path.exists(source_path) else {}
                smb_files = self._get_smb_files(share_name, target_path)
                
                # Файлы для скачивания
                for file_info in smb_files:
                    smb_path = file_info['path']
                    rel_path = os.path.relpath(smb_path, target_path).replace("\\", "/")
                    
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
                        if self._need_download(share_name, smb_path, local_file_path, config_id, rel_path):
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
                    smb_path = os.path.join(target_path, rel_path).replace("\\", "/")
                    
                    # Проверяем, существует ли файл на SMB-ресурсе
                    file_exists = False
                    for file_info in smb_files:
                        if file_info['path'] == smb_path:
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

SMBSync = SMBSyncManager
