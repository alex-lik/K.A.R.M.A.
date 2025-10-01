import os
import sys
import logging
import traceback
import json
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Dict, List, Tuple, Optional, Callable, Any, Union

class ErrorHandler:
    """Система логирования и обработки ошибок"""
    
    def __init__(self, app_name: str = "FileSyncApp", log_dir: str = "logs", 
                 log_level: int = logging.INFO, email_config: Optional[Dict[str, Any]] = None):
        """
        Инициализация обработчика ошибок
        
        Args:
            app_name (str): Имя приложения
            log_dir (str): Директория для хранения логов
            log_level (int): Уровень логирования
            email_config (Optional[Dict[str, Any]]): Конфигурация для отправки уведомлений по email
        """
        self.app_name = app_name
        self.log_dir = log_dir
        self.log_level = log_level
        self.logger = None
        self.error_callbacks = []
        self.email_config = email_config
        self.error_stats = {
            'total_errors': 0,
            'errors_by_type': {},
            'errors_by_module': {},
            'recent_errors': []
        }
        
        self._handlers = []
        
        # Создаем директорию для логов, если она не существует
        os.makedirs(log_dir, exist_ok=True)
        
        # Настраиваем логирование
        self._setup_logging()
        
        # Устанавливаем обработчик необработанных исключений
        sys.excepthook = self.handle_exception
    
    def _setup_logging(self):
        """Настройка системы логирования"""
        # Создаем логгер
        self.logger = logging.getLogger(self.app_name)
        self.logger.setLevel(self.log_level)
        
        # Очищаем существующие обработчики
        self.logger.handlers.clear()
        
        # Формат логов
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Обработчик для вывода в консоль
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        self._handlers.append(console_handler)
        
        # Обработчик для записи в файл (с ротацией по размеру)
        file_handler = RotatingFileHandler(
            os.path.join(self.log_dir, f"{self.app_name}.log"),
            maxBytes=10 * 1024 * 1024,  # 10 МБ
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self._handlers.append(file_handler)
        
        # Обработчик для записи ошибок в отдельный файл (с ротацией по времени)
        error_file_handler = TimedRotatingFileHandler(
            os.path.join(self.log_dir, f"{self.app_name}_errors.log"),
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(formatter)
        self.logger.addHandler(error_file_handler)
        self._handlers.append(error_file_handler)
        
        # Обработчик для записи в формате JSON (для анализа)
        json_file_handler = RotatingFileHandler(
            os.path.join(self.log_dir, f"{self.app_name}_json.log"),
            maxBytes=10 * 1024 * 1024,  # 10 МБ
            backupCount=5,
            encoding='utf-8'
        )
        json_file_handler.setLevel(self.log_level)
        json_file_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(json_file_handler)
        self._handlers.append(json_file_handler)
    
    def add_error_callback(self, callback: Callable[[type, BaseException, Any], None]):
        """
        Добавление функции обратного вызова для обработки ошибок
        
        Args:
            callback (Callable[[type, BaseException, Any], None]): Функция обратного вызова
        """
        self.error_callbacks.append(callback)
    
    def remove_error_callback(self, callback: Callable[[type, BaseException, Any], None]):
        """
        Удаление функции обратного вызова
        
        Args:
            callback (Callable[[type, BaseException, Any], None]): Функция обратного вызова
        """
        if callback in self.error_callbacks:
            self.error_callbacks.remove(callback)
    
    def handle_exception(self, exc_type: type, exc_value: BaseException, exc_traceback: Any):
        """
        Обработка необработанных исключений
        
        Args:
            exc_type (type): Тип исключения
            exc_value (BaseException): Значение исключения
            exc_traceback (Any): Трассировка исключения
        """
        # Формируем сообщение об ошибке
        error_msg = f"Необработанное исключение: {exc_type.__name__}: {exc_value}"
        
        # Записываем в лог
        self.logger.error(error_msg)
        
        # Записываем трассировку
        tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.logger.error(tb_str)
        
        # Обновляем статистику ошибок
        self._update_error_stats(exc_type, exc_value, exc_traceback)
        
        # Отправляем уведомление по email, если настроено
        if self.email_config:
            self._send_error_email(error_msg, tb_str)
        
        # Вызываем функции обратного вызова
        for callback in self.error_callbacks:
            try:
                callback(exc_type, exc_value, exc_traceback)
            except Exception as e:
                self.logger.error(f"Ошибка в функции обратного вызова: {e}")
    
    def log_error(self, message: str, exc_info: Optional[Any] = None, 
                 module: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
        """
        Запись ошибки в лог
        
        Args:
            message (str): Сообщение об ошибке
            exc_info (Optional[Any]): Информация об исключении
            module (Optional[str]): Имя модуля
            extra (Optional[Dict[str, Any]]): Дополнительная информация
        """
        # Добавляем дополнительную информацию в запись лога
        log_extra = {}
        if module:
            log_extra['module'] = module
        if extra:
            log_extra.update(extra)
        
        if exc_info:
            self.logger.error(message, exc_info=exc_info, extra=log_extra)
            
            # Обновляем статистику ошибок
            exc_type, exc_value, exc_traceback = exc_info
            self._update_error_stats(exc_type, exc_value, exc_traceback, module)
        else:
            self.logger.error(message, extra=log_extra)
    
    def log_warning(self, message: str, module: Optional[str] = None, 
                   extra: Optional[Dict[str, Any]] = None):
        """
        Запись предупреждения в лог
        
        Args:
            message (str): Сообщение предупреждения
            module (Optional[str]): Имя модуля
            extra (Optional[Dict[str, Any]]): Дополнительная информация
        """
        # Добавляем дополнительную информацию в запись лога
        log_extra = {}
        if module:
            log_extra['module'] = module
        if extra:
            log_extra.update(extra)
        
        self.logger.warning(message, extra=log_extra)
    
    def log_info(self, message: str, module: Optional[str] = None, 
                extra: Optional[Dict[str, Any]] = None):
        """
        Запись информационного сообщения в лог
        
        Args:
            message (str): Информационное сообщение
            module (Optional[str]): Имя модуля
            extra (Optional[Dict[str, Any]]): Дополнительная информация
        """
        # Добавляем дополнительную информацию в запись лога
        log_extra = {}
        if module:
            log_extra['module'] = module
        if extra:
            log_extra.update(extra)
        
        self.logger.info(message, extra=log_extra)
    
    def log_debug(self, message: str, module: Optional[str] = None, 
                 extra: Optional[Dict[str, Any]] = None):
        """
        Запись отладочного сообщения в лог
        
        Args:
            message (str): Отладочное сообщение
            module (Optional[str]): Имя модуля
            extra (Optional[Dict[str, Any]]): Дополнительная информация
        """
        # Добавляем дополнительную информацию в запись лога
        log_extra = {}
        if module:
            log_extra['module'] = module
        if extra:
            log_extra.update(extra)
        
        self.logger.debug(message, extra=log_extra)
    
    def get_error_log(self, days: int = 7) -> List[str]:
        """
        Получение записей об ошибках за указанный период
        
        Args:
            days (int): Количество дней для выборки
            
        Returns:
            List[str]: Список записей об ошибках
        """
        error_log_path = os.path.join(self.log_dir, f"{self.app_name}_errors.log")
        
        if not os.path.exists(error_log_path):
            return []
        
        # Вычисляем дату начала выборки
        start_date = datetime.now() - timedelta(days=days)
        
        errors = []
        
        try:
            with open(error_log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # Парсим дату из строки лога
                    try:
                        log_date_str = line.split(' - ')[0]
                        log_date = datetime.strptime(log_date_str, '%Y-%m-%d %H:%M:%S')
                        
                        # Если запись новее указанной даты, добавляем в результат
                        if log_date >= start_date:
                            errors.append(line.strip())
                    except Exception:
                        # Если не удалось распарсить дату, добавляем строку в результат
                        errors.append(line.strip())
        except Exception as e:
            self.logger.error(f"Ошибка при чтении лога ошибок: {e}")
        
        return errors
    
    def get_error_stats(self) -> Dict[str, Any]:
        """
        Получение статистики ошибок
        
        Returns:
            Dict[str, Any]: Статистика ошибок
        """
        return self.error_stats.copy()
    
    def close(self):
        """Release logging resources so files can be deleted safely."""
        if not self.logger:
            return
        for handler in list(self._handlers):
            try:
                self.logger.removeHandler(handler)
                handler.close()
            except Exception:
                pass
        self._handlers.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def clear_error_stats(self):
        """Очистка статистики ошибок"""
        self.error_stats = {
            'total_errors': 0,
            'errors_by_type': {},
            'errors_by_module': {},
            'recent_errors': []
        }
        
    
    def clear_old_logs(self, days: int = 30):
        """Remove log entries and stale log files older than the requested age."""
        reopen_logging = False
        try:
            if self._handlers:
                self.close()
                reopen_logging = True

            threshold_date = datetime.now() - timedelta(days=days)

            primary_logs = (
                f"{self.app_name}.log",
                f"{self.app_name}_errors.log",
                f"{self.app_name}_json.log",
            )
            for log_name in primary_logs:
                log_path = os.path.join(self.log_dir, log_name)
                if os.path.exists(log_path):
                    self._clear_old_log_entries(log_path, threshold_date)

            self._remove_old_backup_files(threshold_date)
            self.logger.info("Removed log entries older than %d days", days)

        except Exception as exc:
            self.logger.error("Failed to clear old logs: %s", exc)
        finally:
            if reopen_logging:
                self._setup_logging()

    def _clear_old_log_entries(self, log_path: str, threshold_date: datetime):
        """
        Очистка старых записей в файле лога
        
        Args:
            log_path (str): Путь к файлу лога
            threshold_date (datetime): Пороговая дата
        """
        temp_path = f"{log_path}.tmp"
        
        try:
            with open(log_path, 'r', encoding='utf-8') as src_file:
                with open(temp_path, 'w', encoding='utf-8') as dst_file:
                    for line in src_file:
                        try:
                            # Парсим дату из строки лога
                            log_date_str = line.split(' - ')[0]
                            log_date = datetime.strptime(log_date_str, '%Y-%m-%d %H:%M:%S')
                            
                            # Если запись новее пороговой даты, записываем в новый файл
                            if log_date >= threshold_date:
                                dst_file.write(line)
                        except Exception:
                            # Если не удалось распарсить дату, записываем строку в новый файл
                            dst_file.write(line)
            
            # Заменяем исходный файл новым
            os.replace(temp_path, log_path)
            
        except Exception as e:
            self.logger.error(f"Ошибка при очистке записей в файле {log_path}: {e}")
            
            # Удаляем временный файл, если он существует
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    
    def _remove_old_backup_files(self, threshold_date: datetime):
        """Delete outdated backup log files from the log directory."""
        protected = {
            f"{self.app_name}.log",
            f"{self.app_name}_errors.log",
            f"{self.app_name}_json.log",
        }
        try:
            for filename in os.listdir(self.log_dir):
                file_path = os.path.join(self.log_dir, filename)
                if not os.path.isfile(file_path):
                    continue
                if filename in protected:
                    continue
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mtime >= threshold_date:
                    continue

                should_remove = False
                if filename.endswith('.log') or filename.endswith('.log.gz'):
                    should_remove = True
                elif filename.startswith(f'{self.app_name}.log.'):
                    should_remove = True
                elif filename.startswith(f'{self.app_name}_errors.log.'):
                    should_remove = True
                elif filename.startswith(f'{self.app_name}_json.log.'):
                    should_remove = True

                if should_remove:
                    try:
                        os.remove(file_path)
                        self.logger.debug(f"Removed old log file: {filename}")
                    except Exception as exc:
                        self.logger.error(f"Failed to remove log {filename}: {exc}")
        except Exception as exc:
            self.logger.error(f"Failed to remove old log backups: {exc}")

    def _update_error_stats(self, exc_type: type, exc_value: BaseException, 
                           exc_traceback: Any, module: Optional[str] = None):
        """
        Обновление статистики ошибок
        
        Args:
            exc_type (type): Тип исключения
            exc_value (BaseException): Значение исключения
            exc_traceback (Any): Трассировка исключения
            module (Optional[str]): Имя модуля
        """
        try:
            # Увеличиваем счетчик общего количества ошибок
            self.error_stats['total_errors'] += 1
            
            # Обновляем статистику по типам ошибок
            error_type = exc_type.__name__
            if error_type not in self.error_stats['errors_by_type']:
                self.error_stats['errors_by_type'][error_type] = 0
            self.error_stats['errors_by_type'][error_type] += 1
            
            # Обновляем статистику по модулям
            if module:
                if module not in self.error_stats['errors_by_module']:
                    self.error_stats['errors_by_module'][module] = 0
                self.error_stats['errors_by_module'][module] += 1
            
            # Добавляем ошибку в список последних ошибок
            error_info = {
                'type': error_type,
                'message': str(exc_value),
                'module': module,
                'timestamp': datetime.now().isoformat()
            }
            
            self.error_stats['recent_errors'].append(error_info)
            
            # Ограничиваем размер списка последних ошибок
            if len(self.error_stats['recent_errors']) > 100:
                self.error_stats['recent_errors'] = self.error_stats['recent_errors'][-100:]
                
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении статистики ошибок: {e}")
    
    def _send_error_email(self, subject: str, body: str):
        """
        Отправка уведомления об ошибке по email
        
        Args:
            subject (str): Тема письма
            body (str): Тело письма
        """
        if not self.email_config:
            return
        
        try:
            # Создаем сообщение
            msg = MIMEMultipart()
            msg['From'] = self.email_config.get('from')
            msg['To'] = self.email_config.get('to')
            msg['Subject'] = f"[{self.app_name} Error] {subject}"
            
            # Добавляем тело письма
            msg.attach(MIMEText(body, 'plain'))
            
            # Подключаемся к серверу и отправляем письмо
            server = smtplib.SMTP(
                self.email_config.get('smtp_server'),
                self.email_config.get('smtp_port', 587)
            )
            server.starttls()
            server.login(
                self.email_config.get('username'),
                self.email_config.get('password')
            )
            server.send_message(msg)
            server.quit()
            
            self.logger.info("Отправлено уведомление об ошибке по email")
            
        except Exception as e:
            self.logger.error(f"Ошибка при отправке уведомления об ошибке по email: {e}")
    
    def set_log_level(self, level: int):
        """
        Установка уровня логирования
        
        Args:
            level (int): Уровень логирования
        """
        self.log_level = level
        self.logger.setLevel(level)
        
        # Обновляем уровень для всех обработчиков
        for handler in self.logger.handlers:
            handler.setLevel(level)
    
    def export_logs(self, output_path: str, days: int = 7, 
                   log_type: str = 'all') -> bool:
        """
        Экспорт логов в файл
        
        Args:
            output_path (str): Путь для сохранения файла
            days (int): Количество дней для экспорта
            log_type (str): Тип логов ('all', 'errors', 'json')
            
        Returns:
            bool: True, если экспорт успешен
        """
        try:
            # Вычисляем дату начала выборки
            start_date = datetime.now() - timedelta(days=days)
            
            with open(output_path, 'w', encoding='utf-8') as out_file:
                if log_type in ['all', 'main']:
                    # Экспортируем основные логи
                    main_log_path = os.path.join(self.log_dir, f"{self.app_name}.log")
                    if os.path.exists(main_log_path):
                        out_file.write(f"=== Основные логи ({self.app_name}.log) ===\n\n")
                        self._export_log_entries(main_log_path, out_file, start_date)
                        out_file.write("\n\n")
                
                if log_type in ['all', 'errors']:
                    # Экспортируем логи ошибок
                    error_log_path = os.path.join(self.log_dir, f"{self.app_name}_errors.log")
                    if os.path.exists(error_log_path):
                        out_file.write(f"=== Логи ошибок ({self.app_name}_errors.log) ===\n\n")
                        self._export_log_entries(error_log_path, out_file, start_date)
                        out_file.write("\n\n")
                
                if log_type in ['all', 'json']:
                    # Экспортируем JSON логи
                    json_log_path = os.path.join(self.log_dir, f"{self.app_name}_json.log")
                    if os.path.exists(json_log_path):
                        out_file.write(f"=== JSON логи ({self.app_name}_json.log) ===\n\n")
                        self._export_log_entries(json_log_path, out_file, start_date)
                        out_file.write("\n\n")
            
            self.logger.info(f"Логи экспортированы в файл: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при экспорте логов: {e}")
            return False
    
    def _export_log_entries(self, log_path: str, out_file, start_date: datetime):
        """
        Экспорт записей из файла лога
        
        Args:
            log_path (str): Путь к файлу лога
            out_file: Файл для записи
            start_date (datetime): Начальная дата для выборки
        """
        try:
            with open(log_path, 'r', encoding='utf-8') as src_file:
                for line in src_file:
                    try:
                        # Парсим дату из строки лога
                        log_date_str = line.split(' - ')[0]
                        log_date = datetime.strptime(log_date_str, '%Y-%m-%d %H:%M:%S')
                        
                        # Если запись новее указанной даты, записываем в файл
                        if log_date >= start_date:
                            out_file.write(line)
                    except Exception:
                        # Если не удалось распарсить дату, записываем строку в файл
                        out_file.write(line)
        except Exception as e:
            self.logger.error(f"Ошибка при экспорте записей из файла {log_path}: {e}")


class JSONFormatter(logging.Formatter):
    """Форматтер для вывода логов в формате JSON"""
    
    def format(self, record):
        """
        Форматирование записи лога в формате JSON
        
        Args:
            record: Запись лога
            
        Returns:
            str: Отформатированная запись в формате JSON
        """
        log_object = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage()
        }
        
        # Добавляем информацию об исключении, если есть
        if record.exc_info:
            log_object['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Добавляем дополнительную информацию, если есть
        if hasattr(record, 'extra') and record.extra:
            log_object.update(record.extra)
        
        return json.dumps(log_object, ensure_ascii=False)

