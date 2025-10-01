# K.A.R.M.A - Keep All Records Mirrored Automatically / Автоматическое зеркалирование всех записей
[Русский](#русский) | [English](#english)

---

## Русский

Универсальная система синхронизации файлов с поддержкой множества протоколов и удобным веб-интерфейсом.

### 🚀 Возможности

- **Множественные протоколы**: Локальные файлы, FTP, SMB, AWS S3, Google Drive, Dropbox
- **Веб-интерфейс**: Современный UI на базе NiceGUI для управления конфигурациями
- **Мониторинг в реальном времени**: Автоматическое отслеживание изменений файлов
- **Планировщик задач**: Гибкая настройка расписания синхронизации
- **Безопасность**: Шифрование учетных данных
- **История**: Детальное логирование всех операций синхронизации

### 📋 Требования

- Python 3.8+
- Установленные зависимости из `requirements.txt`

### 🔧 Установка

```bash
# Клонировать репозиторий
git clone <repository-url>
cd K.A.R.M.A

# Установить зависимости
pip install -r requirements.txt
```

### 🎯 Запуск

```bash
python run.py
```

После запуска откройте браузер по адресу `http://localhost:8080`

### 📁 Структура проекта

```
K.A.R.M.A/
├── run.py                 # Точка входа приложения
├── nicegui_app.py        # Веб-интерфейс
├── orchestrator.py       # Координатор синхронизации
├── sync_service.py       # Базовый сервис синхронизации
├── sync_scheduler.py     # Планировщик задач
├── file_monitor.py       # Мониторинг файлов
├── database.py           # Управление БД
├── encryption.py         # Шифрование данных
├── error_handler.py      # Обработка ошибок
├── constants.py          # Константы приложения
└── utils/                # Модули протоколов
    ├── sync_local.py     # Локальная синхронизация
    ├── sync_ftp.py       # FTP
    ├── sync_smb.py       # SMB/CIFS
    ├── sync_s3.py        # AWS S3
    ├── sync_gdrive.py    # Google Drive
    ├── sync_dropbox.py   # Dropbox
    └── utils.py          # Утилиты
```

### 🔑 Основные компоненты

**Оркестратор** (`orchestrator.py`) - Центральный координатор, управляющий всеми операциями синхронизации.

**Сервис синхронизации** (`sync_service.py`) - Базовый класс для реализации различных протоколов синхронизации.

**База данных** (`database.py`) - SQLite-хранилище для конфигураций, истории и состояний файлов.

**Планировщик** (`sync_scheduler.py`) - Управление автоматическими задачами синхронизации по расписанию.

**Мониторинг файлов** (`file_monitor.py`) - Отслеживание изменений в файловой системе в реальном времени.

### 📝 Использование

1. **Создание конфигурации**:
   - Откройте веб-интерфейс
   - Перейдите в раздел "Конфигурации"
   - Нажмите "Добавить" и заполните параметры

2. **Типы синхронизации**:
   - **Односторонняя**: Только из источника в целевое хранилище
   - **Двухсторонняя**: Синхронизация в обе стороны

3. **Режимы работы**:
   - **Ручной**: Запуск по требованию
   - **По расписанию**: Автоматический запуск по расписанию
   - **Реального времени**: Мгновенная синхронизация при изменениях

4. **Настройки фильтрации**:
   - Игнорирование скрытых файлов
   - Маски исключений
   - Проверка целостности

### 🛡️ Безопасность

- Все учетные данные хранятся в зашифрованном виде
- Используется библиотека `cryptography` для шифрования
- Ключ шифрования генерируется автоматически при первом запуске

### 📊 Мониторинг и логи

- История всех операций синхронизации сохраняется в БД
- Подробная статистика по каждой синхронизации
- Информация об ошибках и их деталях

### 🤝 Вклад в проект

Приветствуются любые предложения по улучшению проекта!

### 📄 Лицензия

Проект распространяется по лицензии MIT.

---

## English

Universal file synchronization system with support for multiple protocols and convenient web interface.

### 🚀 Features

- **Multiple Protocols**: Local files, FTP, SMB, AWS S3, Google Drive, Dropbox
- **Web Interface**: Modern NiceGUI-based UI for configuration management
- **Real-time Monitoring**: Automatic file change detection
- **Task Scheduler**: Flexible synchronization scheduling
- **Security**: Encrypted credential storage
- **History**: Detailed logging of all synchronization operations

### 📋 Requirements

- Python 3.8+
- Dependencies installed from `requirements.txt`

### 🔧 Installation

```bash
# Clone the repository
git clone <repository-url>
cd K.A.R.M.A

# Install dependencies
pip install -r requirements.txt
```

### 🎯 Running

```bash
python run.py
```

After startup, open your browser at `http://localhost:8080`

### 📁 Project Structure

```
K.A.R.M.A/
├── run.py                 # Application entry point
├── nicegui_app.py        # Web interface
├── orchestrator.py       # Synchronization coordinator
├── sync_service.py       # Base synchronization service
├── sync_scheduler.py     # Task scheduler
├── file_monitor.py       # File monitoring
├── database.py           # Database management
├── encryption.py         # Data encryption
├── error_handler.py      # Error handling
├── constants.py          # Application constants
└── utils/                # Protocol modules
    ├── sync_local.py     # Local synchronization
    ├── sync_ftp.py       # FTP
    ├── sync_smb.py       # SMB/CIFS
    ├── sync_s3.py        # AWS S3
    ├── sync_gdrive.py    # Google Drive
    ├── sync_dropbox.py   # Dropbox
    └── utils.py          # Utilities
```

### 🔑 Main Components

**Orchestrator** (`orchestrator.py`) - Central coordinator managing all synchronization operations.

**Sync Service** (`sync_service.py`) - Base class for implementing various synchronization protocols.

**Database** (`database.py`) - SQLite storage for configurations, history, and file states.

**Scheduler** (`sync_scheduler.py`) - Management of automatic scheduled synchronization tasks.

**File Monitor** (`file_monitor.py`) - Real-time file system change tracking.

### 📝 Usage

1. **Creating Configuration**:
   - Open the web interface
   - Navigate to "Configurations" section
   - Click "Add" and fill in parameters

2. **Synchronization Types**:
   - **One-way**: Only from source to target storage
   - **Two-way**: Bidirectional synchronization

3. **Operation Modes**:
   - **Manual**: Run on demand
   - **Scheduled**: Automatic execution by schedule
   - **Real-time**: Instant synchronization on changes

4. **Filter Settings**:
   - Ignore hidden files
   - Exclusion masks
   - Integrity verification

### 🛡️ Security

- All credentials are stored encrypted
- Uses `cryptography` library for encryption
- Encryption key is generated automatically on first run

### 📊 Monitoring and Logs

- History of all synchronization operations stored in DB
- Detailed statistics for each synchronization
- Error information and details

### 🤝 Contributing

All suggestions for project improvement are welcome!

### 📄 License

Project is distributed under the MIT License.

---

**Note / Примечание**: For proper cloud services operation (Google Drive, Dropbox), you need to configure appropriate API keys and access tokens. / Для корректной работы с облачными сервисами необходимо настроить соответствующие API ключи и токены доступа.

## ✨ Authors / Авторы

alex-lik
