#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль с константами для приложения FileSync
"""

# Версия приложения
APP_VERSION = "1.0.0"
APP_NAME = "FileSync"
APP_AUTHOR = "FileSync Team"
APP_WEBSITE = "https://github.com/yourusername/filesync"

# Значения по умолчанию
DEFAULT_FILE_BUFFER_SIZE = 8192  # байт
DEFAULT_LOG_LEVEL = "info"
DEFAULT_LOG_RETENTION_DAYS = 30

# Ограничения
MAX_FILENAME_LENGTH = 255
MAX_PATH_LENGTH = 4096

# Уровни логирования
LOG_LEVEL_DEBUG = "debug"
LOG_LEVEL_INFO = "info"
LOG_LEVEL_WARNING = "warning"
LOG_LEVEL_ERROR = "error"
LOG_LEVEL_CRITICAL = "critical"

# Локализация
DEFAULT_LANGUAGE = "en"  # Язык по умолчанию: 'ru' или 'en'
AVAILABLE_LANGUAGES = ["ru", "en"]
