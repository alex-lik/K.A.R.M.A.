import os
import time
import logging
import threading
import schedule
from datetime import datetime, timedelta
from queue import Queue, Empty
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

from src.core.database import DatabaseManager
from src.sync.utils import FileUtils, TimeUtils, CryptoUtils, NetworkUtils

logger = logging.getLogger(__name__)

class SyncScheduler:
    """Планировщик синхронизации по расписанию"""
    
    def __init__(self, db_manager: DatabaseManager, sync_manager, error_handler=None):
        """
        Инициализация планировщика синхронизации
        
        Args:
            db_manager (DatabaseManager): Менеджер базы данных
            sync_manager: Менеджер синхронизации
        """
        self.db_manager = db_manager
        self.sync_manager = sync_manager
        self.error_handler = error_handler
        self.running = False
        self.scheduler_thread = None
        self.worker_thread = None
        self.task_queue = Queue()
        self.active_tasks = {}
        self.lock = threading.Lock()
        self.schedules = {}
        self.max_concurrent_tasks = 3  # Максимальное количество одновременных задач
        self.task_timeout = 3600  # Таймаут выполнения задачи в секундах (1 час)
        
    def start(self) -> bool:
        """
        Запуск планировщика
        
        Returns:
            bool: True, если запуск успешен
        """
        with self.lock:
            if self.running:
                logger.warning("Планировщик уже запущен")
                return False
            
            self.running = True
            
            # Запускаем поток планировщика
            self.scheduler_thread = threading.Thread(target=self._run_scheduler)
            self.scheduler_thread.daemon = True
            self.scheduler_thread.start()
            
            # Запускаем рабочий поток для выполнения задач
            self.worker_thread = threading.Thread(target=self._process_tasks)
            self.worker_thread.daemon = True
            self.worker_thread.start()
            
            # Запускаем поток для проверки таймаутов задач
            self.timeout_thread = threading.Thread(target=self._check_task_timeouts)
            self.timeout_thread.daemon = True
            self.timeout_thread.start()
            
            logger.info("Планировщик синхронизации запущен")
            return True
    
    def stop(self) -> bool:
        """
        Остановка планировщика
        
        Returns:
            bool: True, если остановка успешна
        """
        with self.lock:
            if not self.running:
                logger.warning("Планировщик не запущен")
                return False
            
            self.running = False
            
            # Добавляем задачу для пробуждения потоков
            for _ in range(3):  # Добавляем несколько задач для пробуждения всех потоков
                self.task_queue.put(None)
            
            # Ждем завершения потоков
            if self.scheduler_thread:
                self.scheduler_thread.join(timeout=5)
            
            if self.worker_thread:
                self.worker_thread.join(timeout=5)
            
            # Очищаем расписание
            schedule.clear()
            
            logger.info("Планировщик синхронизации остановлен")
            return True
    
    def add_schedule(self, config_id: int, schedule_type: str, schedule_value: str) -> bool:
        """
        Добавление расписания для конфигурации синхронизации
        
        Args:
            config_id (int): ID конфигурации синхронизации
            schedule_type (str): Тип расписания (interval, daily, weekly, monthly)
            schedule_value (str): Значение расписания в зависимости от типа
            
        Returns:
            bool: True, если расписание добавлено успешно
        """
        with self.lock:
            if not self.running:
                logger.error("Планировщик не запущен")
                return False
            
            # Проверяем существование конфигурации
            config = self.db_manager.get_sync_config(config_id)
            if not config:
                logger.error(f"Не найдена конфигурация с ID: {config_id}")
                return False
            
            # Удаляем старое расписание, если оно существует
            if config_id in self.schedules:
                self.remove_schedule(config_id)
            
            try:
                # Создаем задание в зависимости от типа расписания
                job = None
                
                if schedule_type == 'interval':
                    # Расписание с интервалом в минутах
                    interval_minutes = int(schedule_value)
                    job = schedule.every(interval_minutes).minutes.do(
                        self._enqueue_sync_task, config_id
                    )
                
                elif schedule_type == 'daily':
                    # Ежедневное расписание в указанное время
                    daily_time = schedule_value  # Формат: HH:MM
                    job = schedule.every().day.at(daily_time).do(
                        self._enqueue_sync_task, config_id
                    )
                
                elif schedule_type == 'weekly':
                    # Еженедельное расписание в указанный день и время
                    # Формат: день недели,HH:MM (например: monday,10:30)
                    day, time_str = schedule_value.split(',')
                    job = getattr(schedule.every(), day.lower()).at(time_str).do(
                        self._enqueue_sync_task, config_id
                    )
                
                elif schedule_type == 'monthly':
                    # Ежемесячное расписание в указанный день и время
                    # Формат: день месяца,HH:MM (например: 15,10:30)
                    day, time_str = schedule_value.split(',')
                    day_of_month = int(day)
                    
                    # Для ежемесячного расписания используем специальную функцию
                    job = schedule.every().day.at(time_str).do(
                        self._check_monthly_sync, config_id, day_of_month
                    )
                
                elif schedule_type == 'custom':
                    # Пользовательское расписание в формате cron
                    # В данном случае мы просто добавляем задачу, которая будет выполняться каждый день
                    # в указанное время, но с дополнительной проверкой в функции
                    job = schedule.every().day.at("00:00").do(
                        self._check_custom_sync, config_id, schedule_value
                    )
                
                else:
                    logger.error(f"Неизвестный тип расписания: {schedule_type}")
                    return False
                
                # Сохраняем задание
                self.schedules[config_id] = {
                    'job': job,
                    'type': schedule_type,
                    'value': schedule_value
                }
                
                # Обновляем информацию о расписании в базе данных
                self.db_manager.update_sync_schedule(
                    config_id=config_id,
                    schedule_type=schedule_type,
                    schedule_value=schedule_value,
                    enabled=True
                )
                
                logger.info(f"Добавлено расписание для конфигурации {config_id}: {schedule_type} {schedule_value}")
                return True
                
            except Exception as e:
                logger.error(f"Ошибка при добавлении расписания для конфигурации {config_id}: {e}")
                return False
    
    def remove_schedule(self, config_id: int) -> bool:
        """
        Удаление расписания для конфигурации синхронизации
        
        Args:
            config_id (int): ID конфигурации синхронизации
            
        Returns:
            bool: True, если расписание удалено успешно
        """
        with self.lock:
            if config_id not in self.schedules:
                logger.warning(f"Расписание для конфигурации {config_id} не найдено")
                return False
            
            try:
                # Удаляем задание из расписания
                schedule.cancel_job(self.schedules[config_id]['job'])
                
                # Удаляем из словаря
                del self.schedules[config_id]
                
                # Обновляем информацию о расписании в базе данных
                self.db_manager.update_sync_schedule(
                    config_id=config_id,
                    schedule_type=None,
                    schedule_value=None,
                    enabled=False
                )
                
                logger.info(f"Удалено расписание для конфигурации {config_id}")
                return True
                
            except Exception as e:
                logger.error(f"Ошибка при удалении расписания для конфигурации {config_id}: {e}")
                return False
    
    def run_sync_now(self, config_id: int) -> bool:
        """
        Немедленный запуск синхронизации для указанной конфигурации
        
        Args:
            config_id (int): ID конфигурации синхронизации
            
        Returns:
            bool: True, если задача добавлена в очередь
        """
        with self.lock:
            if not self.running:
                logger.error("Планировщик не запущен")
                return False
            
            # Проверяем существование конфигурации
            config = self.db_manager.get_sync_config(config_id)
            if not config:
                logger.error(f"Не найдена конфигурация с ID: {config_id}")
                return False
            
            # Проверяем, не выполняется ли уже задача для этой конфигурации
            if config_id in self.active_tasks:
                logger.warning(f"Синхронизация для конфигурации {config_id} уже выполняется")
                return False
            
            # Проверяем, не превышено ли количество одновременных задач
            if len(self.active_tasks) >= self.max_concurrent_tasks:
                logger.warning(f"Достигнуто максимальное количество одновременных задач: {self.max_concurrent_tasks}")
                return False
            
            # Добавляем задачу в очередь
            self.task_queue.put({
                'type': 'sync',
                'config_id': config_id,
                'timestamp': datetime.now()
            })
            
            logger.info(f"Добавлена задача на немедленную синхронизацию для конфигурации {config_id}")
            return True
    
    def get_active_tasks(self) -> Dict[int, Dict[str, Any]]:
        """
        Получение списка активных задач
        
        Returns:
            Dict[int, Dict[str, Any]]: Информация об активных задачах
        """
        with self.lock:
            return self.active_tasks.copy()
    
    def get_schedules(self) -> Dict[int, Dict[str, Any]]:
        """
        Получение списка расписаний
        
        Returns:
            Dict[int, Dict[str, Any]]: Информация о расписаниях
        """
        with self.lock:
            schedules_info = {}
            for config_id, schedule_info in self.schedules.items():
                schedules_info[config_id] = {
                    'type': schedule_info['type'],
                    'value': schedule_info['value'],
                    'next_run': schedule_info['job'].next_run
                }
            return schedules_info
    
    def load_schedules_from_db(self):
        """Загрузка расписаний из базы данных"""
        try:
            # Получаем все конфигурации с включенным расписанием
            configs = self.db_manager.get_all_sync_configs()
            
            for config in configs:
                if config.get('schedule_enabled') and config.get('schedule_type'):
                    # Добавляем расписание
                    self.add_schedule(
                        config_id=config['id'],
                        schedule_type=config['schedule_type'],
                        schedule_value=config['schedule_value']
                    )
            
            logger.info(f"Загружено {len(self.schedules)} расписаний из базы данных")
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке расписаний из базы данных: {e}")
    
    def _run_scheduler(self):
        """Поток выполнения планировщика"""
        while self.running:
            try:
                # Выполняем запланированные задачи
                schedule.run_pending()
                
                # Пауза для уменьшения нагрузки на CPU
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Ошибка в потоке планировщика: {e}")
    
    def _process_tasks(self):
        """Поток обработки задач"""
        while self.running:
            try:
                # Получаем задачу из очереди с таймаутом
                task = self.task_queue.get(timeout=1)
                
                if task is None:
                    # Сигнал для завершения потока
                    break
                
                # Обрабатываем задачу
                self._handle_task(task)
                
            except Empty:
                # Таймаут при ожидании задачи
                continue
            except Exception as e:
                logger.error(f"Ошибка при обработке задачи: {e}")
    
    def _check_task_timeouts(self):
        """Поток для проверки таймаутов задач"""
        while self.running:
            try:
                time.sleep(60)  # Проверяем каждую минуту
                
                with self.lock:
                    current_time = datetime.now()
                    tasks_to_remove = []
                    
                    for config_id, task_info in self.active_tasks.items():
                        start_time = task_info['start_time']
                        elapsed_time = (current_time - start_time).total_seconds()
                        
                        if elapsed_time > self.task_timeout:
                            logger.warning(f"Задача для конфигурации {config_id} превышает таймаут")
                            tasks_to_remove.append(config_id)
                            
                            # Записываем ошибку в историю
                            self.db_manager.add_sync_history(
                                config_id=config_id,
                                status='timeout',
                                message=f"Задача превышает таймаут ({self.task_timeout} секунд)",
                                start_time=start_time,
                                end_time=current_time
                            )
                    
                    # Удаляем задачи с таймаутом
                    for config_id in tasks_to_remove:
                        del self.active_tasks[config_id]
                
            except Exception as e:
                logger.error(f"Ошибка при проверке таймаутов задач: {e}")
    
    def _handle_task(self, task: Dict[str, Any]):
        """
        Обработка задачи
        
        Args:
            task (Dict[str, Any]): Информация о задаче
        """
        try:
            task_type = task['type']
            config_id = task['config_id']
            timestamp = task['timestamp']
            
            if task_type == 'sync':
                # Задача синхронизации
                self._handle_sync_task(config_id, timestamp)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке задачи: {e}")
    
    def _handle_sync_task(self, config_id: int, timestamp: datetime):
        """
        Обработка задачи синхронизации
        
        Args:
            config_id (int): ID конфигурации синхронизации
            timestamp (datetime): Время создания задачи
        """
        try:
            # Получаем информацию о конфигурации
            config = self.db_manager.get_sync_config(config_id)
            if not config:
                logger.error(f"Не найдена конфигурация с ID: {config_id}")
                return
            
            # Добавляем задачу в список активных
            with self.lock:
                self.active_tasks[config_id] = {
                    'start_time': datetime.now(),
                    'status': 'running'
                }
            
            # Записываем начало синхронизации в историю
            history_id = self.db_manager.add_sync_history(
                config_id=config_id,
                status='running',
                message="Начало синхронизации по расписанию",
                start_time=datetime.now()
            )
            
            # Выполняем синхронизацию
            result = self.sync_manager.sync_config(config_id)
            
            # Обновляем статус задачи
            status = 'completed' if result else 'failed'
            
            # Обновляем информацию в истории
            self.db_manager.update_sync_history(
                history_id=history_id,
                status=status,
                message=f"Завершение синхронизации по расписанию: {status}",
                end_time=datetime.now()
            )
            
            # Удаляем задачу из списка активных
            with self.lock:
                if config_id in self.active_tasks:
                    del self.active_tasks[config_id]
            
            logger.info(f"Завершена синхронизация для конфигурации {config_id}: {status}")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении синхронизации для конфигурации {config_id}: {e}")
            
            # Обновляем статус задачи на 'failed'
            with self.lock:
                if config_id in self.active_tasks:
                    self.active_tasks[config_id]['status'] = 'failed'
                    del self.active_tasks[config_id]
            
            # Записываем ошибку в историю
            self.db_manager.add_sync_history(
                config_id=config_id,
                status='failed',
                message=f"Ошибка при синхронизации: {e}",
                start_time=timestamp,
                end_time=datetime.now()
            )
    
    def _enqueue_sync_task(self, config_id: int):
        """
        Добавление задачи синхронизации в очередь
        
        Args:
            config_id (int): ID конфигурации синхронизации
        """
        with self.lock:
            # Проверяем, не выполняется ли уже задача для этой конфигурации
            if config_id in self.active_tasks:
                logger.warning(f"Синхронизация для конфигурации {config_id} уже выполняется, пропуск")
                return
            
            # Проверяем, не превышено ли количество одновременных задач
            if len(self.active_tasks) >= self.max_concurrent_tasks:
                logger.warning(f"Достигнуто максимальное количество одновременных задач: {self.max_concurrent_tasks}")
                return
            
            # Добавляем задачу в очередь
            self.task_queue.put({
                'type': 'sync',
                'config_id': config_id,
                'timestamp': datetime.now()
            })
            
            logger.info(f"Добавлена задача на синхронизацию для конфигурации {config_id}")
    
    def _check_monthly_sync(self, config_id: int, day_of_month: int):
        """
        Проверка и запуск ежемесячной синхронизации
        
        Args:
            config_id (int): ID конфигурации синхронизации
            day_of_month (int): День месяца для синхронизации
        """
        # Получаем текущий день месяца
        current_day = datetime.now().day
        
        # Если сегодня нужный день, запускаем синхронизацию
        if current_day == day_of_month:
            self._enqueue_sync_task(config_id)
    
    def _check_custom_sync(self, config_id: int, cron_expression: str):
        """
        Проверка и запуск синхронизации по пользовательскому расписанию
        
        Args:
            config_id (int): ID конфигурации синхронизации
            cron_expression (str): Выражение cron
        """
        # В данной реализации мы просто проверяем, что текущее время соответствует
        # простому формату "час:минута"
        try:
            hour, minute = map(int, cron_expression.split(':'))
            current_time = datetime.now()
            
            if current_time.hour == hour and current_time.minute == minute:
                self._enqueue_sync_task(config_id)
        except Exception as e:
            logger.error(f"Ошибка при проверке пользовательского расписания: {e}")