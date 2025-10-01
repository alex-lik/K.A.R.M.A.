
import os
import time
import logging
import threading
import shutil
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from src.core.database import DatabaseManager
from src.sync.utils import FileUtils, TimeUtils, CryptoUtils, NetworkUtils

logger = logging.getLogger(__name__)

class FileChangeHandler(FileSystemEventHandler):
    """Обработчик событий файловой системы"""
    
    def __init__(self, callback: Callable[[str, str, Optional[str]], None]):
        """
        Инициализация обработчика событий файловой системы
        
        Args:
            callback (Callable[[str, str, Optional[str]], None]): Функция обратного вызова для обработки событий
        """
        self.callback = callback
        super().__init__()
    
    def on_created(self, event):
        """Обработка события создания файла/папки"""
        logger.debug(f"🆕 FileChangeHandler.on_created: {event.src_path} (is_dir={event.is_directory})")
        if not event.is_directory:
            self.callback('created', event.src_path)

    def on_modified(self, event):
        """Обработка события изменения файла/папки"""
        logger.debug(f"✏️ FileChangeHandler.on_modified: {event.src_path} (is_dir={event.is_directory})")
        if not event.is_directory:
            self.callback('modified', event.src_path)

    def on_deleted(self, event):
        """Обработка события удаления файла/папки"""
        logger.debug(f"🗑️ FileChangeHandler.on_deleted: {event.src_path} (is_dir={event.is_directory})")
        if not event.is_directory:
            self.callback('deleted', event.src_path)

    def on_moved(self, event):
        """Обработка события перемещения файла/папки"""
        logger.debug(f"📦 FileChangeHandler.on_moved: {event.src_path} -> {event.dest_path} (is_dir={event.is_directory})")
        if not event.is_directory:
            self.callback('moved', event.src_path, event.dest_path)

class FileMonitor:
    """Монитор изменений файловой системы в реальном времени"""
    
    def __init__(self, db_manager: DatabaseManager, error_handler=None, sync_callback=None):
        """
        Инициализация монитора файловой системы

        Args:
            db_manager (DatabaseManager): Менеджер базы данных
            error_handler: Обработчик ошибок
            sync_callback: Callback функция для запуска синхронизации (принимает config_id)
        """
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.sync_callback = sync_callback
        self.observers = {}
        self.event_queue = Queue()
        self.running = False
        self.worker_thread = None
        self.lock = threading.Lock()
        self.debounce_time = 5.0  # Время в секундах для подавления повторных событий (увеличено для растущих файлов)
        self.last_events = {}  # Словарь для отслеживания последних событий
        self.file_sizes = {}  # Отслеживание размеров файлов для определения завершения записи
        
    def start(self) -> bool:
        """
        Запуск монитора
        
        Returns:
            bool: True, если запуск успешен
        """
        if not WATCHDOG_AVAILABLE:
            logger.error("Модуль watchdog не установлен. Установите watchdog")
            return False
        
        with self.lock:
            if self.running:
                logger.warning("Монитор уже запущен")
                return False
            
            self.running = True
            
            # Запускаем рабочий поток для обработки событий
            self.worker_thread = threading.Thread(target=self._process_events)
            self.worker_thread.daemon = True
            self.worker_thread.start()
            
            logger.info("Монитор файловой системы запущен")
            return True
    
    def stop(self) -> bool:
        """
        Остановка монитора
        
        Returns:
            bool: True, если остановка успешна
        """
        with self.lock:
            if not self.running:
                logger.warning("Монитор не запущен")
                return False
            
            self.running = False
            
            # Останавливаем всех наблюдателей
            for path, observer in self.observers.items():
                observer.stop()
                observer.join()
            
            self.observers.clear()
            
            # Добавляем событие для пробуждения рабочего потока
            self.event_queue.put(None)
            
            # Ждем завершения рабочего потока
            if self.worker_thread:
                self.worker_thread.join(timeout=5)
            
            logger.info("Монитор файловой системы остановлен")
            return True
    
    def add_watch(self, path: str, config_id: int) -> bool:
        """
        Добавление пути для мониторинга
        
        Args:
            path (str): Путь к папке для мониторинга
            config_id (int): ID конфигурации синхронизации
            
        Returns:
            bool: True, если путь добавлен успешно
        """
        if not WATCHDOG_AVAILABLE:
            logger.error("Модуль watchdog не установлен. Установите watchdog")
            return False
        
        with self.lock:
            if not self.running:
                logger.error("Монитор не запущен")
                return False
            
            # Проверяем, не отслеживается ли уже этот путь
            if path in self.observers:
                logger.warning(f"Путь {path} уже отслеживается")
                return False
            
            # Проверяем существование пути
            if not os.path.exists(path):
                logger.error(f"Путь не существует: {path}")
                return False
            
            try:
                # Создаем наблюдателя
                observer = Observer()
                event_handler = FileChangeHandler(
                    lambda event_type, src_path, dest_path=None: self._on_file_event(
                        event_type, src_path, dest_path, config_id
                    )
                )
                
                # Добавляем путь для наблюдения
                observer.schedule(event_handler, path, recursive=True)
                observer.start()
                
                # Сохраняем наблюдателя
                self.observers[path] = observer
                
                logger.info(f"Добавлен путь для мониторинга: {path}")
                return True
                
            except Exception as e:
                logger.error(f"Ошибка при добавлении пути для мониторинга {path}: {e}")
                return False
    
    def remove_watch(self, path: str) -> bool:
        """
        Удаление пути из мониторинга
        
        Args:
            path (str): Путь к папке для удаления из мониторинга
            
        Returns:
            bool: True, если путь удален успешно
        """
        with self.lock:
            if path not in self.observers:
                logger.warning(f"Путь {path} не отслеживается")
                return False
            
            try:
                # Останавливаем наблюдателя
                observer = self.observers[path]
                observer.stop()
                observer.join()
                
                # Удаляем наблюдателя из словаря
                del self.observers[path]
                
                logger.info(f"Удален путь из мониторинга: {path}")
                return True
                
            except Exception as e:
                logger.error(f"Ошибка при удалении пути из мониторинга {path}: {e}")
                return False
    
    def _on_file_event(self, event_type: str, src_path: str, dest_path: Optional[str], config_id: int):
        """
        Обработчик события файловой системы

        Args:
            event_type (str): Тип события (created, modified, deleted, moved)
            src_path (str): Исходный путь
            dest_path (Optional[str]): Целевой путь (для события moved)
            config_id (int): ID конфигурации синхронизации
        """
        logger.info(f"🔔 Получено событие: {event_type} для {src_path} (config={config_id})")

        # Пропускаем скрытые файлы и папки
        if os.path.basename(src_path).startswith('.'):
            logger.debug(f"Пропущен скрытый файл: {src_path}")
            return

        # Для события moved также проверяем целевой путь
        if event_type == 'moved' and dest_path and os.path.basename(dest_path).startswith('.'):
            logger.debug(f"Пропущен скрытый файл при перемещении: {dest_path}")
            return

        # Добавляем событие в очередь для обработки
        event = {
            'type': event_type,
            'src_path': src_path,
            'dest_path': dest_path,
            'config_id': config_id,
            'timestamp': datetime.now()
        }
        self.event_queue.put(event)
        logger.info(f"📥 Событие добавлено в очередь: {event_type} - {src_path}")
    
    def _process_events(self):
        """Обработка событий из очереди"""
        from queue import Empty
        while self.running:
            try:
                # Получаем событие из очереди с таймаутом
                event = self.event_queue.get(timeout=1)

                if event is None:
                    # Сигнал для завершения потока
                    break

                # Обрабатываем событие с подавлением дребезга
                self._handle_event_with_debounce(event)

            except Empty:
                # Таймаут - нормальная ситуация, продолжаем
                continue
            except Exception as e:
                logger.exception(f"❌ Ошибка при обработке события файловой системы: {e}")
    
    def _handle_event_with_debounce(self, event: Dict[str, Any]):
        """
        Обработка события файловой системы с подавлением дребезга

        Args:
            event (Dict[str, Any]): Информация о событии
        """
        try:
            event_type = event['type']
            src_path = event['src_path']
            config_id = event['config_id']
            timestamp = event['timestamp']

            # Создаем ключ для идентификации события
            event_key = f"{event_type}:{src_path}"

            # Проверяем, было ли недавно подобное событие
            if event_key in self.last_events:
                last_time = self.last_events[event_key]
                time_diff = (timestamp - last_time).total_seconds()

                if time_diff < self.debounce_time:
                    # Пропускаем событие, так как оно слишком частое
                    logger.debug(f"⏭️ Пропущено повторное событие {event_key} (debounce={time_diff:.2f}s)")
                    return

            logger.info(f"✅ Обрабатываем событие {event_type} для {src_path}")

            # Обновляем время последнего события
            self.last_events[event_key] = timestamp

            # Обрабатываем событие
            self._handle_event(event)

        except Exception as e:
            logger.error(f"Ошибка при обработке события файловой системы с подавлением дребезга: {e}")
    
    def _handle_event(self, event: Dict[str, Any]):
        """
        Обработка события файловой системы
        
        Args:
            event (Dict[str, Any]): Информация о событии
        """
        try:
            event_type = event['type']
            src_path = event['src_path']
            dest_path = event.get('dest_path')
            config_id = event['config_id']
            timestamp = event['timestamp']
            
            # Получаем информацию о конфигурации
            config = self.db_manager.get_sync_config(config_id)
            if not config:
                logger.error(f"Не найдена конфигурация с ID: {config_id}")
                return
            
            # Определяем относительный путь файла
            source_path = config['source_path']
            
            # Проверяем, что путь находится внутри отслеживаемой папки
            try:
                rel_path = os.path.relpath(src_path, source_path)
                
                # Проверяем, что путь не выходит за пределы отслеживаемой папки
                if rel_path.startswith('..'):
                    return
            except ValueError:
                # Пути на разных дисках в Windows
                return
            
            # Обрабатываем событие в зависимости от типа
            if event_type == 'created':
                logger.info(f"Обнаружен новый файл: {src_path}")
                self._handle_file_created(config_id, rel_path, timestamp)
            
            elif event_type == 'modified':
                logger.info(f"Обнаружено изменение файла: {src_path}")
                self._handle_file_modified(config_id, rel_path, timestamp)
            
            elif event_type == 'deleted':
                logger.info(f"Обнаружено удаление файла: {src_path}")
                self._handle_file_deleted(config_id, rel_path, timestamp)
            
            elif event_type == 'moved':
                if dest_path:
                    # Проверяем, что целевой путь находится внутри отслеживаемой папки
                    try:
                        dest_rel_path = os.path.relpath(dest_path, source_path)
                        
                        # Проверяем, что путь не выходит за пределы отслеживаемой папки
                        if dest_rel_path.startswith('..'):
                            return
                    except ValueError:
                        # Пути на разных дисках в Windows
                        return
                    
                    logger.info(f"Обнаружено перемещение файла: {src_path} -> {dest_path}")
                    self._handle_file_moved(config_id, rel_path, dest_rel_path, timestamp)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке события файловой системы: {e}")
    
    def _handle_file_created(self, config_id: int, rel_path: str, timestamp: datetime):
        """
        Обработка события создания файла
        
        Args:
            config_id (int): ID конфигурации синхронизации
            rel_path (str): Относительный путь к файлу
            timestamp (datetime): Время события
        """
        try:
            # Получаем информацию о файле
            config = self.db_manager.get_sync_config(config_id)
            source_path = config['source_path']
            file_path = os.path.join(source_path, rel_path)
            
            if not os.path.exists(file_path):
                message = f'Файл не существует: {file_path}'
                logger.error(message)
                if self.error_handler:
                    self.error_handler.log_error(message)
                return
            
            # Получаем информацию о файле
            stat = os.stat(file_path)
            current_size = stat.st_size

            # Проверяем, стабилен ли размер файла (для растущих файлов бекапов)
            file_key = f"{config_id}:{rel_path}"

            # Для пустых файлов (0 байт) пропускаем проверку стабильности
            if current_size == 0:
                logger.info(f"✅ Пустой файл {rel_path} (0 байт), готов к синхронизации")
                # Удаляем из отслеживания, если был там
                if file_key in self.file_sizes:
                    del self.file_sizes[file_key]
            elif file_key in self.file_sizes:
                last_size = self.file_sizes[file_key]
                if last_size != current_size:
                    logger.info(f"📈 Файл {rel_path} всё ещё растёт ({last_size} -> {current_size} байт), откладываем синхронизацию")
                    self.file_sizes[file_key] = current_size
                    return
                else:
                    logger.info(f"✅ Размер файла {rel_path} стабилен ({current_size} байт), готов к синхронизации")
                    # Удаляем из отслеживания
                    del self.file_sizes[file_key]
            else:
                # Первое обнаружение - запоминаем размер и ждём следующего события
                logger.info(f"🆕 Новый файл {rel_path} ({current_size} байт), ожидаем стабилизации размера")
                self.file_sizes[file_key] = current_size
                return

            # Обновляем состояние файла в базе данных
            self.db_manager.update_file_state(
                config_id=config_id,
                file_path=rel_path,
                file_hash=None,  # Хеш будет вычислен при синхронизации
                modified_time=stat.st_mtime,
                sync_status='pending'
            )

            # Записываем событие в историю
            self.db_manager.add_sync_history(
                config_id=config_id,
                status='pending',
                message=f"Обнаружен новый файл: {rel_path}",
                start_time=timestamp,
                end_time=timestamp
            )

            # Запускаем синхронизацию
            if self.sync_callback:
                logger.info(f"🚀 Запуск синхронизации для конфигурации {config_id} после создания файла {rel_path}")
                threading.Thread(target=self.sync_callback, args=(config_id,), daemon=True).start()

        except Exception as e:
            message = f'Ошибка при обработке события создания файла: {e}'
            logger.exception(message)
            if self.error_handler:
                self.error_handler.log_error(message)
    
    def _handle_file_modified(self, config_id: int, rel_path: str, timestamp: datetime):
        """
        Обработка события изменения файла
        
        Args:
            config_id (int): ID конфигурации синхронизации
            rel_path (str): Относительный путь к файлу
            timestamp (datetime): Время события
        """
        try:
            # Получаем информацию о файле
            config = self.db_manager.get_sync_config(config_id)
            source_path = config['source_path']
            file_path = os.path.join(source_path, rel_path)
            
            if not os.path.exists(file_path):
                message = f'Файл не существует: {file_path}'
                logger.error(message)
                if self.error_handler:
                    self.error_handler.log_error(message)
                return
            
            # Получаем информацию о файле
            stat = os.stat(file_path)
            current_size = stat.st_size

            # Проверяем, стабилен ли размер файла (для растущих файлов бекапов)
            file_key = f"{config_id}:{rel_path}"

            # Для пустых файлов (0 байт) пропускаем проверку стабильности
            if current_size == 0:
                logger.info(f"✅ Пустой файл {rel_path} (0 байт), готов к синхронизации")
                # Удаляем из отслеживания, если был там
                if file_key in self.file_sizes:
                    del self.file_sizes[file_key]
            elif file_key in self.file_sizes:
                last_size = self.file_sizes[file_key]
                if last_size != current_size:
                    logger.info(f"📈 Файл {rel_path} всё ещё изменяется ({last_size} -> {current_size} байт), откладываем синхронизацию")
                    self.file_sizes[file_key] = current_size
                    return
                else:
                    logger.info(f"✅ Размер файла {rel_path} стабилен ({current_size} байт), готов к синхронизации")
                    # Удаляем из отслеживания
                    del self.file_sizes[file_key]
            else:
                # Первое обнаружение изменения - запоминаем размер
                logger.info(f"✏️ Файл {rel_path} изменён ({current_size} байт), ожидаем стабилизации размера")
                self.file_sizes[file_key] = current_size
                return

            # Обновляем состояние файла в базе данных
            self.db_manager.update_file_state(
                config_id=config_id,
                file_path=rel_path,
                file_hash=None,  # Хеш будет вычислен при синхронизации
                modified_time=stat.st_mtime,
                sync_status='pending'
            )

            # Записываем событие в историю
            self.db_manager.add_sync_history(
                config_id=config_id,
                status='pending',
                message=f"Обнаружено изменение файла: {rel_path}",
                start_time=timestamp,
                end_time=timestamp
            )

            # Запускаем синхронизацию
            if self.sync_callback:
                logger.info(f"🚀 Запуск синхронизации для конфигурации {config_id} после изменения файла {rel_path}")
                threading.Thread(target=self.sync_callback, args=(config_id,), daemon=True).start()

        except Exception as e:
            message = f'Ошибка при обработке события изменения файла: {e}'
            logger.exception(message)
            if self.error_handler:
                self.error_handler.log_error(message)
    
    def _handle_file_deleted(self, config_id: int, rel_path: str, timestamp: datetime):
        """
        Обработка события удаления файла

        Args:
            config_id (int): ID конфигурации синхронизации
            rel_path (str): Относительный путь к файлу
            timestamp (datetime): Время события
        """
        try:
            # Удаляем состояние файла из базы данных
            self.db_manager.delete_file_state(config_id, rel_path)

            # Записываем событие в историю
            self.db_manager.add_sync_history(
                config_id=config_id,
                status='pending',
                message=f"Обнаружено удаление файла: {rel_path}",
                start_time=timestamp,
                end_time=timestamp
            )

            # Запускаем синхронизацию
            if self.sync_callback:
                logger.info(f"🚀 Запуск синхронизации для конфигурации {config_id} после удаления файла {rel_path}")
                threading.Thread(target=self.sync_callback, args=(config_id,), daemon=True).start()

        except Exception as e:
            message = f'Ошибка при обработке события удаления файла: {e}'
            logger.exception(message)
            if self.error_handler:
                self.error_handler.log_error(message)
    
    def _handle_file_moved(self, config_id: int, src_rel_path: str, dest_rel_path: str, timestamp: datetime):
        """
        Обработка события перемещения файла

        Args:
            config_id (int): ID конфигурации синхронизации
            src_rel_path (str): Относительный исходный путь к файлу
            dest_rel_path (str): Относительный целевой путь к файлу
            timestamp (datetime): Время события
        """
        try:
            # Получаем информацию о конфигурации
            config = self.db_manager.get_sync_config(config_id)
            source_path = config['source_path']

            # Удаляем состояние старого файла
            self.db_manager.delete_file_state(config_id, src_rel_path)

            # Получаем информацию о новом файле
            dest_path = os.path.join(source_path, dest_rel_path)
            if os.path.exists(dest_path):
                stat = os.stat(dest_path)

                # Добавляем состояние нового файла
                self.db_manager.update_file_state(
                    config_id=config_id,
                    file_path=dest_rel_path,
                    file_hash=None,  # Хеш будет вычислен при синхронизации
                    modified_time=stat.st_mtime,
                    sync_status='pending'
                )

            # Записываем событие в историю
            self.db_manager.add_sync_history(
                config_id=config_id,
                status='pending',
                message=f"Обнаружено перемещение файла: {src_rel_path} -> {dest_rel_path}",
                start_time=timestamp,
                end_time=timestamp
            )

            # Запускаем синхронизацию
            if self.sync_callback:
                logger.info(f"🚀 Запуск синхронизации для конфигурации {config_id} после перемещения файла {src_rel_path} -> {dest_rel_path}")
                threading.Thread(target=self.sync_callback, args=(config_id,), daemon=True).start()

        except Exception as e:
            message = f'Ошибка при обработке события перемещения файла: {e}'
            logger.exception(message)
            if self.error_handler:
                self.error_handler.log_error(message)
    
    def get_pending_files(self, config_id: int) -> List[str]:
        """
        Получение списка файлов, ожидающих синхронизации
        
        Args:
            config_id (int): ID конфигурации синхронизации
            
        Returns:
            List[str]: Список относительных путей к файлам
        """
        try:
            file_states = self.db_manager.get_file_states(config_id)
            pending_files = [
                state['file_path'] for state in file_states 
                if state['sync_status'] == 'pending'
            ]
            return pending_files
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов, ожидающих синхронизации: {e}")
            return []
    
    def get_watched_paths(self) -> List[Tuple[str, int]]:
        """
        Получение списка отслеживаемых путей
        
        Returns:
            List[Tuple[str, int]]: Список кортежей (путь, ID конфигурации)
        """
        try:
            watched_paths = []
            for path, observer in self.observers.items():
                # Получаем ID конфигурации из обработчика событий
                # Это немного сложно, так как мы не храним эту информацию напрямую
                # В реальном приложении можно было бы улучшить эту часть
                for config_id in self.db_manager.get_all_config_ids():
                    config = self.db_manager.get_sync_config(config_id)
                    if config and config['source_path'] == path:
                        watched_paths.append((path, config_id))
                        break
            
            return watched_paths
        except Exception as e:
            logger.error(f"Ошибка при получении списка отслеживаемых путей: {e}")
            return []
    
    def clear_old_events(self, max_age_hours: int = 24):
        """
        Очистка старых событий из словаря последних событий
        
        Args:
            max_age_hours (int): Максимальный возраст событий в часах
        """
        try:
            current_time = datetime.now()
            max_age_seconds = max_age_hours * 3600
            
            # Удаляем старые события
            events_to_remove = []
            for event_key, timestamp in self.last_events.items():
                age_seconds = (current_time - timestamp).total_seconds()
                if age_seconds > max_age_seconds:
                    events_to_remove.append(event_key)
            
            for event_key in events_to_remove:
                del self.last_events[event_key]
            
            logger.debug(f"Очищено {len(events_to_remove)} старых событий")
            
        except Exception as e:
            logger.error(f"Ошибка при очистке старых событий: {e}")