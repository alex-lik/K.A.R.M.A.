#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль локализации для приложения FileSync
"""

from typing import Dict, Any


class Localization:
    """Класс для управления локализацией приложения"""

    def __init__(self, language: str = 'ru'):
        """
        Инициализация локализации

        Args:
            language: Код языка ('ru' или 'en')
        """
        self.language = language
        self._translations = self._load_translations()

    def _load_translations(self) -> Dict[str, Dict[str, Any]]:
        """Загрузка всех переводов"""
        return {
            'ru': {
                # Общее
                'app_name': 'FileSync',
                'app_subtitle': 'Система резервного копирования и синхронизации',
                'version': 'v1.0.0',
                'copyright': '© FileSync 2025 | Система резервного копирования',
                'database': 'База данных',

                # Кнопки
                'btn_add': '➕ Добавить задачу',
                'btn_refresh': '🔄 Обновить',
                'btn_refresh_services': '🔄 Обновить службы',
                'btn_sync': '🔄 Синхронизировать',
                'btn_edit': '✏️ Редактировать',
                'btn_toggle': '⏸️/▶️ Вкл/Выкл',
                'btn_delete': '🗑️ Удалить',
                'btn_refresh_list': '🔄 Обновить список',
                'btn_browse': '📁 Обзор',
                'btn_test_connection': '🔌 Тестировать подключение',
                'btn_cancel': '❌ Отмена',
                'btn_save': '💾 Сохранить',

                # Вкладки
                'tab_configs': '📋 Конфигурации',
                'tab_history': '📊 История',
                'tab_logs': '📄 Журналы',
                'tab_status': '⚙️ Службы',

                # Конфигурации
                'config_title': 'Управление задачами синхронизации',
                'config_new': '➕ Новая конфигурация синхронизации',
                'config_edit': '✏️ Редактирование конфигурации',

                # Поля конфигурации
                'field_name': 'Название конфигурации',
                'field_name_hint': 'Например: Документы на R2',
                'field_description': 'Описание (необязательно)',
                'field_source': 'Путь к папке',
                'field_source_hint': 'Локальная папка для синхронизации',
                'field_target_folder': 'Целевая папка',
                'field_target_folder_hint': 'Папка назначения',

                # Секции
                'section_basic': '📝 Основная информация',
                'section_source': '📂 Источник синхронизации',
                'section_target': '🎯 Назначение',
                'section_settings': '⚙️ Дополнительные параметры',

                # Типы хранилищ
                'target_local': '📁 Локальная папка',
                'target_s3': '🪣 S3 / Cloudflare R2',
                'target_ftp': '🌐 FTP/FTPS',
                'target_smb': '💻 SMB/CIFS',
                'target_gdrive': '☁️ Google Drive',
                'target_dropbox': '📦 Dropbox',
                'target_type': 'Тип хранилища',

                # Настройки S3
                's3_settings': '🔑 Настройки подключения S3 / Cloudflare R2',
                's3_endpoint': 'Endpoint URL',
                's3_endpoint_hint': 'Например: https://your-account-id.r2.cloudflarestorage.com',
                's3_access_key': 'Access Key',
                's3_secret_key': 'Secret Key',
                's3_bucket': 'Bucket Name',
                's3_bucket_hint': 'Имя bucket',
                's3_region': 'Region',
                's3_region_hint': 'Регион (auto для R2)',
                's3_prefix': 'Prefix (необязательно)',
                's3_prefix_hint': 'Префикс пути в bucket, например: backups/documents/',

                # Настройки FTP
                'ftp_settings': '🌐 Настройки FTP-сервера',
                'ftp_server': 'Сервер',
                'ftp_server_hint': 'IP или домен',
                'ftp_port': 'Порт',
                'ftp_username': 'Логин',
                'ftp_password': 'Пароль',
                'ftp_folder': 'Папка на сервере',
                'ftp_folder_hint': 'Путь на FTP-сервере',
                'ftp_use_ssl': 'Использовать FTPS (SSL/TLS)',

                # Настройки SMB
                'smb_settings': '💻 Настройки SMB/CIFS (сетевая папка)',
                'smb_server': 'Сервер',
                'smb_server_hint': 'IP или имя сервера',
                'smb_port': 'Порт',
                'smb_username': 'Логин',
                'smb_password': 'Пароль',
                'smb_domain': 'Домен (необязательно)',
                'smb_share': 'Сетевая папка (Share)',
                'smb_share_hint': 'Имя сетевой папки',
                'smb_path': 'Путь внутри Share',
                'smb_path_hint': 'Подпапка внутри сетевой папки',

                # Настройки Google Drive
                'gdrive_settings': '☁️ Настройки Google Drive',
                'gdrive_credentials': 'Файл учетных данных (credentials.json)',
                'gdrive_credentials_hint': 'OAuth2 credentials из Google Cloud Console',
                'gdrive_folder': 'Папка в Google Drive',
                'gdrive_folder_hint': 'ID папки или \'/\' для корня',

                # Настройки Dropbox
                'dropbox_settings': '📦 Настройки Dropbox',
                'dropbox_token': 'Access Token',
                'dropbox_token_hint': 'Токен доступа из https://www.dropbox.com/developers',
                'dropbox_folder': 'Папка в Dropbox',
                'dropbox_folder_hint': 'Путь к папке в Dropbox',

                # Дополнительные параметры
                'param_realtime': '👁️ Мониторинг в реальном времени',
                'param_realtime_hint': 'Автоматическая синхронизация при изменении файлов',
                'param_delete': '🗑️ Удалять отсутствующие файлы',
                'param_delete_hint': 'Удалять файлы в назначении, которых нет в источнике',
                'param_active': '✅ Конфигурация активна',

                # Статусы
                'status_active': '🟢 Активна',
                'status_inactive': '⚫ Неактивна',
                'status_monitoring': '👁️ Мониторинг',
                'status_completed': 'completed',
                'status_failed': 'failed',
                'status_running': 'running',

                # Таблица конфигураций
                'col_id': 'ID',
                'col_name': 'Название',
                'col_source': 'Источник',
                'col_target': 'Назначение',
                'col_status': 'Статус',

                # Таблица истории
                'history_title': 'История синхронизаций',
                'history_period': 'Период:',
                'history_days': 'дней',
                'col_config': 'Конфигурация',
                'col_files': 'Файлов',
                'col_start_time': 'Начало',

                # Журналы
                'logs_title': 'Журналы приложения',
                'logs_select': 'Выберите файл журнала',
                'logs_content': 'Содержимое',
                'logs_no_file': 'Выберите файл журнала',
                'logs_error': 'Не удалось прочитать файл',

                # Службы
                'services_title': 'Состояние служб',
                'services_active': '🔄 Активные задачи синхронизации',
                'services_monitoring': '👁️ Мониторинг каталогов',
                'services_no_tasks': 'Нет активных задач',
                'services_no_monitoring': 'Мониторинг не активен',

                # Уведомления
                'notify_select_config': '⚠️ Выберите конфигурацию в таблице',
                'notify_config_not_found': '⚠️ Конфигурация не найдена',
                'notify_sync_start': '🔄 Запуск синхронизации',
                'notify_sync_success': '✅ Синхронизация завершена успешно',
                'notify_sync_error': '❌ Синхронизация завершилась с ошибкой',
                'notify_config_activated': '✅ Конфигурация активирована',
                'notify_config_deactivated': '✅ Конфигурация деактивирована',
                'notify_config_deleted': '🗑️ Конфигурация удалена',
                'notify_config_saved': '✅ Конфигурация обновлена',
                'notify_config_added': '✅ Конфигурация добавлена',
                'notify_name_required': '⚠️ Укажите название конфигурации',
                'notify_source_required': '⚠️ Укажите папку для синхронизации',
                'notify_target_required': '⚠️ Укажите целевую папку',
                'notify_test_running': '🔄 Тестирование подключения...',
                'notify_error': '❌ Ошибка',

                # Диалоги
                'dialog_delete_confirm': 'Удалить конфигурацию "{}"?\n\nЭто действие нельзя отменить!',

                # Диалоги выбора
                'dialog_select_folder': 'Выберите папку',
                'dialog_select_source': 'Выберите папку для синхронизации',
                'dialog_select_target': 'Выберите целевую папку',
                'dialog_select_file': 'Выберите файл',
                'dialog_select_credentials': 'Выберите credentials.json',
            },
            'en': {
                # General
                'app_name': 'FileSync',
                'app_subtitle': 'Backup and Synchronization System',
                'version': 'v1.0.0',
                'copyright': '© FileSync 2025 | Backup System',
                'database': 'Database',

                # Buttons
                'btn_add': '➕ Add Task',
                'btn_refresh': '🔄 Refresh',
                'btn_refresh_services': '🔄 Refresh Services',
                'btn_sync': '🔄 Synchronize',
                'btn_edit': '✏️ Edit',
                'btn_toggle': '⏸️/▶️ Toggle',
                'btn_delete': '🗑️ Delete',
                'btn_refresh_list': '🔄 Refresh List',
                'btn_browse': '📁 Browse',
                'btn_test_connection': '🔌 Test Connection',
                'btn_cancel': '❌ Cancel',
                'btn_save': '💾 Save',

                # Tabs
                'tab_configs': '📋 Configurations',
                'tab_history': '📊 History',
                'tab_logs': '📄 Logs',
                'tab_status': '⚙️ Services',

                # Configurations
                'config_title': 'Sync Task Management',
                'config_new': '➕ New Sync Configuration',
                'config_edit': '✏️ Edit Configuration',

                # Configuration fields
                'field_name': 'Configuration Name',
                'field_name_hint': 'Example: Documents to R2',
                'field_description': 'Description (optional)',
                'field_source': 'Folder Path',
                'field_source_hint': 'Local folder to synchronize',
                'field_target_folder': 'Target Folder',
                'field_target_folder_hint': 'Destination folder',

                # Sections
                'section_basic': '📝 Basic Information',
                'section_source': '📂 Sync Source',
                'section_target': '🎯 Destination',
                'section_settings': '⚙️ Additional Settings',

                # Storage types
                'target_local': '📁 Local Folder',
                'target_s3': '🪣 S3 / Cloudflare R2',
                'target_ftp': '🌐 FTP/FTPS',
                'target_smb': '💻 SMB/CIFS',
                'target_gdrive': '☁️ Google Drive',
                'target_dropbox': '📦 Dropbox',
                'target_type': 'Storage Type',

                # S3 Settings
                's3_settings': '🔑 S3 / Cloudflare R2 Connection Settings',
                's3_endpoint': 'Endpoint URL',
                's3_endpoint_hint': 'Example: https://your-account-id.r2.cloudflarestorage.com',
                's3_access_key': 'Access Key',
                's3_secret_key': 'Secret Key',
                's3_bucket': 'Bucket Name',
                's3_bucket_hint': 'Bucket name',
                's3_region': 'Region',
                's3_region_hint': 'Region (auto for R2)',
                's3_prefix': 'Prefix (optional)',
                's3_prefix_hint': 'Path prefix in bucket, e.g.: backups/documents/',

                # FTP Settings
                'ftp_settings': '🌐 FTP Server Settings',
                'ftp_server': 'Server',
                'ftp_server_hint': 'IP or domain',
                'ftp_port': 'Port',
                'ftp_username': 'Username',
                'ftp_password': 'Password',
                'ftp_folder': 'Server Folder',
                'ftp_folder_hint': 'Path on FTP server',
                'ftp_use_ssl': 'Use FTPS (SSL/TLS)',

                # SMB Settings
                'smb_settings': '💻 SMB/CIFS Settings (Network Share)',
                'smb_server': 'Server',
                'smb_server_hint': 'IP or server name',
                'smb_port': 'Port',
                'smb_username': 'Username',
                'smb_password': 'Password',
                'smb_domain': 'Domain (optional)',
                'smb_share': 'Network Share',
                'smb_share_hint': 'Share name',
                'smb_path': 'Path inside Share',
                'smb_path_hint': 'Subfolder inside network share',

                # Google Drive Settings
                'gdrive_settings': '☁️ Google Drive Settings',
                'gdrive_credentials': 'Credentials File (credentials.json)',
                'gdrive_credentials_hint': 'OAuth2 credentials from Google Cloud Console',
                'gdrive_folder': 'Google Drive Folder',
                'gdrive_folder_hint': 'Folder ID or \'/\' for root',

                # Dropbox Settings
                'dropbox_settings': '📦 Dropbox Settings',
                'dropbox_token': 'Access Token',
                'dropbox_token_hint': 'Access token from https://www.dropbox.com/developers',
                'dropbox_folder': 'Dropbox Folder',
                'dropbox_folder_hint': 'Path to folder in Dropbox',

                # Additional parameters
                'param_realtime': '👁️ Real-time Monitoring',
                'param_realtime_hint': 'Automatic synchronization on file changes',
                'param_delete': '🗑️ Delete Missing Files',
                'param_delete_hint': 'Delete files in destination that don\'t exist in source',
                'param_active': '✅ Configuration Active',

                # Statuses
                'status_active': '🟢 Active',
                'status_inactive': '⚫ Inactive',
                'status_monitoring': '👁️ Monitoring',
                'status_completed': 'completed',
                'status_failed': 'failed',
                'status_running': 'running',

                # Configuration table
                'col_id': 'ID',
                'col_name': 'Name',
                'col_source': 'Source',
                'col_target': 'Destination',
                'col_status': 'Status',

                # History table
                'history_title': 'Synchronization History',
                'history_period': 'Period:',
                'history_days': 'days',
                'col_config': 'Configuration',
                'col_files': 'Files',
                'col_start_time': 'Started',

                # Logs
                'logs_title': 'Application Logs',
                'logs_select': 'Select log file',
                'logs_content': 'Content',
                'logs_no_file': 'Select a log file',
                'logs_error': 'Could not read file',

                # Services
                'services_title': 'Service Status',
                'services_active': '🔄 Active Sync Tasks',
                'services_monitoring': '👁️ Directory Monitoring',
                'services_no_tasks': 'No active tasks',
                'services_no_monitoring': 'Monitoring not active',

                # Notifications
                'notify_select_config': '⚠️ Select a configuration in the table',
                'notify_config_not_found': '⚠️ Configuration not found',
                'notify_sync_start': '🔄 Starting synchronization',
                'notify_sync_success': '✅ Synchronization completed successfully',
                'notify_sync_error': '❌ Synchronization failed',
                'notify_config_activated': '✅ Configuration activated',
                'notify_config_deactivated': '✅ Configuration deactivated',
                'notify_config_deleted': '🗑️ Configuration deleted',
                'notify_config_saved': '✅ Configuration updated',
                'notify_config_added': '✅ Configuration added',
                'notify_name_required': '⚠️ Please specify configuration name',
                'notify_source_required': '⚠️ Please specify folder to synchronize',
                'notify_target_required': '⚠️ Please specify target folder',
                'notify_test_running': '🔄 Testing connection...',
                'notify_error': '❌ Error',

                # Dialogs
                'dialog_delete_confirm': 'Delete configuration "{}"?\n\nThis action cannot be undone!',

                # Selection dialogs
                'dialog_select_folder': 'Select Folder',
                'dialog_select_source': 'Select Folder to Synchronize',
                'dialog_select_target': 'Select Target Folder',
                'dialog_select_file': 'Select File',
                'dialog_select_credentials': 'Select credentials.json',
            }
        }

    def get(self, key: str, default: str = '') -> str:
        """
        Получить перевод для ключа

        Args:
            key: Ключ перевода
            default: Значение по умолчанию, если перевод не найден

        Returns:
            Переведенная строка или значение по умолчанию
        """
        return self._translations.get(self.language, {}).get(key, default or key)

    def set_language(self, language: str) -> None:
        """
        Установить язык интерфейса

        Args:
            language: Код языка ('ru' или 'en')
        """
        if language in self._translations:
            self.language = language

    def get_language(self) -> str:
        """
        Получить текущий язык

        Returns:
            Код текущего языка
        """
        return self.language

    def get_available_languages(self) -> Dict[str, str]:
        """
        Получить список доступных языков

        Returns:
            Словарь с кодами и названиями языков
        """
        return {
            'ru': '🇷🇺 Русский',
            'en': '🇬🇧 English'
        }


# Глобальный экземпляр локализации
_localization_instance = None


def get_localization(language: str = None) -> Localization:
    """
    Получить глобальный экземпляр локализации

    Args:
        language: Код языка (опционально)

    Returns:
        Экземпляр класса Localization
    """
    global _localization_instance

    if _localization_instance is None or language is not None:
        from src.core.constants import DEFAULT_LANGUAGE
        _localization_instance = Localization(language or DEFAULT_LANGUAGE)

    return _localization_instance
