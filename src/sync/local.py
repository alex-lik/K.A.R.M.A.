import os
import shutil
import hashlib
import time
from datetime import datetime
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

from src.sync.utils import FileUtils, TimeUtils, CryptoUtils

logger = logging.getLogger(__name__)

class LocalSyncManager:
    """Менеджер синхронизации локальных папок"""
    
    def __init__(self, db_manager, error_handler=None):
        """
        Инициализация менеджера синхронизации
        
        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.sync_stats = {
            'copied': 0,
            'updated': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }
        self.current_sync_id = None
    
    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """
        Вычисление хеша файла для сравнения
        
        Args:
            file_path (str): Путь к файлу
            
        Returns:
            Optional[str]: Хеш файла или None в случае ошибки
        """
        return FileUtils.get_file_hash(file_path, "md5")
    
    def sync_folders(self, config_id: int, source_path: str, target_path: str,
                    callback: Optional[Callable[[str, str], None]] = None,
                    delete_mode: bool = True,
                    history_id: Optional[int] = None) -> Dict[str, int]:
        """
        Синхронизация папок
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к исходной папке
            target_path (str): Путь к целевой папке
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            delete_mode (bool): Удалять ли файлы, отсутствующие в источнике
            
        Returns:
            Dict[str, int]: Статистика синхронизации
        """
        # Сброс статистики
        self.sync_stats = {
            'copied': 0,
            'updated': 0,
            'deleted': 0,
            'skipped': 0,
            'errors': 0
        }

        # Используем переданный history_id или создаем новый
        if history_id:
            self.current_sync_id = history_id
        else:
            self.current_sync_id = self.db_manager.add_sync_history(
                config_id=config_id,
                status='in_progress',
                message=f"Начало синхронизации: {source_path} -> {target_path}"
            )
        
        # Проверяем существование исходной папки
        if not os.path.exists(source_path):
            error_msg = f"Исходная папка не существует: {source_path}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            # Обновление истории синхронизации
            if self.current_sync_id:
                self.db_manager.update_sync_history(
                    history_id=self.current_sync_id,
                    status='error',
                    message=error_msg
                )
            
            return self.sync_stats
        
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
                
                # Обновление истории синхронизации
                if self.current_sync_id:
                    self.db_manager.update_sync_history(
                        history_id=self.current_sync_id,
                        status='error',
                        message=error_msg
                    )
                
                return self.sync_stats
        
        # Получаем список файлов в исходной и целевой папках
        source_files = self._get_files_list(source_path)
        target_files = self._get_files_list(target_path)
        
        # Синхронизируем файлы из исходной папки в целевую
        for rel_path in source_files:
            source_file = os.path.join(source_path, rel_path)
            target_file = os.path.join(target_path, rel_path)
            
            # Создаем подкаталоги, если необходимо
            target_dir = os.path.dirname(target_file)
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
            
            # Проверяем, нужно ли копировать/обновлять файл
            if rel_path not in target_files:
                # Файла нет в целевой папке, копируем
                if self._copy_file(source_file, target_file, callback):
                    self.sync_stats['copied'] += 1

                    # Обновляем состояние файла в базе данных
                    self._update_file_state_in_db(config_id, rel_path, source_file, 'synced')

                    # Логируем операцию
                    if self.current_sync_id:
                        try:
                            file_size = os.path.getsize(source_file) if os.path.exists(source_file) else 0
                            self.db_manager.add_file_operation(
                                history_id=self.current_sync_id,
                                operation_type='copied',
                                file_path=rel_path,
                                source_path=source_file,
                                target_path=target_file,
                                file_size=file_size,
                                status='success'
                            )
                        except Exception as e:
                            logger.error(f"Ошибка при логировании операции копирования: {e}")
            else:
                # Файл есть в обеих папках, проверяем, нужно ли обновлять
                if self._need_update(source_file, target_file, config_id, rel_path):
                    if self._copy_file(source_file, target_file, callback):
                        self.sync_stats['updated'] += 1

                        # Обновляем состояние файла в базе данных
                        self._update_file_state_in_db(config_id, rel_path, source_file, 'synced')

                        # Логируем операцию
                        if self.current_sync_id:
                            try:
                                file_size = os.path.getsize(source_file) if os.path.exists(source_file) else 0
                                self.db_manager.add_file_operation(
                                    history_id=self.current_sync_id,
                                    operation_type='updated',
                                    file_path=rel_path,
                                    source_path=source_file,
                                    target_path=target_file,
                                    file_size=file_size,
                                    status='success'
                                )
                            except Exception as e:
                                logger.error(f"Ошибка при логировании операции обновления: {e}")
                else:
                    self.sync_stats['skipped'] += 1
                    debug_msg = f"Файл пропущен (без изменений): {rel_path}"
                    logger.debug(debug_msg)
                    if callback:
                        callback(debug_msg, "debug")
        
        # Удаляем файлы, которые есть в целевой папке, но отсутствуют в исходной
        # ВАЖНО: удаляем только те файлы, которые система сама синхронизировала (есть в file_states)
        if delete_mode:
            # Получаем список файлов, которые были синхронизированы системой
            synced_files = set()
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                synced_files.add(state['file_path'])

            for rel_path in target_files:
                if rel_path not in source_files:
                    # Удаляем только если этот файл был синхронизирован системой
                    if rel_path in synced_files:
                        target_file = os.path.join(target_path, rel_path)
                        if self._delete_file(target_file, callback):
                            self.sync_stats['deleted'] += 1

                            # Удаляем состояние файла из базы данных
                            self.db_manager.delete_file_state(config_id, rel_path)

                            # Логируем операцию
                            if self.current_sync_id:
                                try:
                                    self.db_manager.add_file_operation(
                                        history_id=self.current_sync_id,
                                        operation_type='deleted',
                                        file_path=rel_path,
                                        source_path=None,
                                        target_path=target_file,
                                        file_size=0,
                                        status='success'
                                    )
                                except Exception as e:
                                    logger.error(f"Ошибка при логировании операции удаления: {e}")
                    else:
                        # Файл не был синхронизирован системой, пропускаем
                        logger.debug(f"Пропущен файл {rel_path} - не был синхронизирован этой системой")
                        if callback:
                            callback(f"Пропущен файл (не синхронизирован системой): {rel_path}", "debug")
        
        # Обновление истории синхронизации
        if self.current_sync_id:
            total_files = self.sync_stats['copied'] + self.sync_stats['updated'] + self.sync_stats['skipped']
            status = 'success' if self.sync_stats['errors'] == 0 else 'error'

            message = f"Синхронизация завершена. " \
                     f"Скопировано: {self.sync_stats['copied']}, " \
                     f"Обновлено: {self.sync_stats['updated']}, " \
                     f"Удалено: {self.sync_stats['deleted']}, " \
                     f"Пропущено: {self.sync_stats['skipped']}, " \
                     f"Ошибок: {self.sync_stats['errors']}"

            self.db_manager.update_sync_history(
                history_id=self.current_sync_id,
                status=status,
                message=message,
                files_count=total_files,
                files_processed=self.sync_stats['copied'] + self.sync_stats['updated'],
                files_copied=self.sync_stats['copied'],
                files_updated=self.sync_stats['updated'],
                files_deleted=self.sync_stats['deleted'],
                errors=self.sync_stats['errors'],
                end_time=datetime.utcnow()
            )
        
        return self.sync_stats
    
    def _get_files_list(self, folder_path: str) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка всех файлов в папке и подпапках
        
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
    
    def _need_update(self, source_file: str, target_file: str, config_id: int, rel_path: str) -> bool:
        """
        Проверка, нужно ли обновлять файл
        
        Args:
            source_file (str): Путь к исходному файлу
            target_file (str): Путь к целевому файлу
            config_id (int): ID конфигурации в базе данных
            rel_path (str): Относительный путь к файлу
            
        Returns:
            bool: True, если файл нужно обновить
        """
        try:
            # Получаем информацию о файлах
            source_stat = os.stat(source_file)
            target_stat = os.stat(target_file)
            
            # Проверяем размер файла
            if source_stat.st_size != target_stat.st_size:
                return True
            
            # Проверяем время модификации
            if source_stat.st_mtime > target_stat.st_mtime:
                return True
            
            # Проверяем хеш файла, если размеры и времена совпадают
            source_hash = self.calculate_file_hash(source_file)
            target_hash = self.calculate_file_hash(target_file)
            
            if source_hash != target_hash:
                return True
            
            # Проверяем состояние файла в базе данных
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                if state['file_path'] == rel_path:
                    # Если хеш в базе отличается от текущего, нужно обновить
                    if state['file_hash'] != source_hash:
                        return True
                    break
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при проверке необходимости обновления файла {source_file}: {e}")
            return True  # В случае ошибки, считаем что файл нужно обновить
    
    def _copy_file(self, source_file: str, target_file: str, 
                  callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Копирование файла
        
        Args:
            source_file (str): Путь к исходному файлу
            target_file (str): Путь к целевому файлу
            callback (Optional[Callable[[str, str], None]]): Функция обратного вызова для обновления прогресса
            
        Returns:
            bool: True, если копирование успешно
        """
        try:
            # Создаем резервную копию целевого файла, если он существует
            backup_created = False
            if os.path.exists(target_file):
                backup_file = target_file + ".bak"
                try:
                    shutil.copy2(target_file, backup_file)
                    backup_created = True
                except Exception as e:
                    logger.warning(f"Не удалось создать резервную копию файла {target_file}: {e}")
            
            # Копируем файл
            shutil.copy2(source_file, target_file)
            
            # Удаляем резервную копию, если она была создана
            if backup_created:
                try:
                    os.remove(target_file + ".bak")
                except Exception as e:
                    logger.warning(f"Не удалось удалить резервную копию файла {target_file}: {e}")
            
            info_msg = f"Скопирован файл: {os.path.basename(source_file)}"
            logger.info(info_msg)
            if callback:
                callback(info_msg, "info")
            
            return True
        except Exception as e:
            error_msg = f"Ошибка при копировании файла {source_file} -> {target_file}: {e}"
            logger.error(error_msg)
            if callback:
                callback(error_msg, "error")
            
            self.sync_stats['errors'] += 1
            return False
    
    def _delete_file(self, file_path: str, 
                    callback: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Удаление файла
        
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
            file_hash = self.calculate_file_hash(file_path)
            file_stat = os.stat(file_path)
            
            self.db_manager.update_file_state(
                config_id=config_id,
                file_path=rel_path,
                file_hash=file_hash,
                modified_time=file_stat.st_mtime,
                sync_status=sync_status
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении состояния файла в базе данных: {e}")
    
    def update_file_states(self, config_id: int, source_path: str):
        """
        Обновление состояний файлов в базе данных
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к исходной папке
        """
        try:
            # Получаем список файлов в исходной папке
            source_files = self._get_files_list(source_path)
            
            # Обновляем состояние каждого файла
            for rel_path in source_files:
                file_path = os.path.join(source_path, rel_path)
                self._update_file_state_in_db(config_id, rel_path, file_path, 'synced')
            
            # Удаляем из базы данных записи о файлах, которых больше нет в исходной папке
            file_states = self.db_manager.get_file_states(config_id)
            for state in file_states:
                if state['file_path'] not in source_files:
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
        summary.append("Статистика синхронизации:")
        summary.append(f"  Скопировано: {self.sync_stats['copied']}")
        summary.append(f"  Обновлено: {self.sync_stats['updated']}")
        summary.append(f"  Удалено: {self.sync_stats['deleted']}")
        summary.append(f"  Пропущено: {self.sync_stats['skipped']}")
        summary.append(f"  Ошибок: {self.sync_stats['errors']}")
        
        return "\n".join(summary)
    
    def compare_folders(self, source_path: str, target_path: str) -> Dict[str, List[str]]:
        """
        Сравнение двух папок и определение различий
        
        Args:
            source_path (str): Путь к исходной папке
            target_path (str): Путь к целевой папке
            
        Returns:
            Dict[str, List[str]]: Словарь с различиями
        """
        result = {
            'only_in_source': [],
            'only_in_target': [],
            'different': [],
            'identical': []
        }
        
        try:
            # Получаем списки файлов
            source_files = self._get_files_list(source_path)
            target_files = self._get_files_list(target_path)
            
            # Файлы, которые есть только в источнике
            for rel_path in source_files:
                if rel_path not in target_files:
                    result['only_in_source'].append(rel_path)
            
            # Файлы, которые есть только в целевой папке
            for rel_path in target_files:
                if rel_path not in source_files:
                    result['only_in_target'].append(rel_path)
            
            # Файлы, которые есть в обеих папках
            for rel_path in source_files:
                if rel_path in target_files:
                    source_file = os.path.join(source_path, rel_path)
                    target_file = os.path.join(target_path, rel_path)
                    
                    # Сравниваем файлы
                    if self._need_update(source_file, target_file, -1, rel_path):
                        result['different'].append(rel_path)
                    else:
                        result['identical'].append(rel_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при сравнении папок: {e}")
            return result
    
    def preview_sync(self, config_id: int, source_path: str, target_path: str) -> Dict[str, Any]:
        """
        Предварительный просмотр синхронизации без выполнения операций
        
        Args:
            config_id (int): ID конфигурации в базе данных
            source_path (str): Путь к исходной папке
            target_path (str): Путь к целевой папке
            
        Returns:
            Dict[str, Any]: Результаты предварительного просмотра
        """
        preview = {
            'to_copy': [],
            'to_update': [],
            'to_delete': [],
            'to_skip': [],
            'errors': []
        }
        
        try:
            # Проверяем существование исходной папки
            if not os.path.exists(source_path):
                preview['errors'].append(f"Исходная папка не существует: {source_path}")
                return preview
            
            # Получаем списки файлов
            source_files = self._get_files_list(source_path)
            target_files = self._get_files_list(target_path) if os.path.exists(target_path) else {}
            
            # Файлы для копирования
            for rel_path in source_files:
                if rel_path not in target_files:
                    source_file = os.path.join(source_path, rel_path)
                    file_info = {
                        'path': rel_path,
                        'size': source_files[rel_path]['size'],
                        'mtime': source_files[rel_path]['mtime']
                    }
                    preview['to_copy'].append(file_info)
                else:
                    source_file = os.path.join(source_path, rel_path)
                    target_file = os.path.join(target_path, rel_path)
                    
                    if self._need_update(source_file, target_file, config_id, rel_path):
                        file_info = {
                            'path': rel_path,
                            'size': source_files[rel_path]['size'],
                            'mtime': source_files[rel_path]['mtime']
                        }
                        preview['to_update'].append(file_info)
                    else:
                        file_info = {
                            'path': rel_path,
                            'size': source_files[rel_path]['size'],
                            'mtime': source_files[rel_path]['mtime']
                        }
                        preview['to_skip'].append(file_info)
            
            # Файлы для удаления
            for rel_path in target_files:
                if rel_path not in source_files:
                    file_info = {
                        'path': rel_path,
                        'size': target_files[rel_path]['size'],
                        'mtime': target_files[rel_path]['mtime']
                    }
                    preview['to_delete'].append(file_info)
            
            return preview
            
        except Exception as e:
            preview['errors'].append(f"Ошибка при предварительном просмотре синхронизации: {e}")
            return preview

LocalSync = LocalSyncManager
