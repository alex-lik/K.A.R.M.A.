from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from tkinter import Tk, filedialog

from nicegui import app, ui

from src.core.database import DatabaseManager
from src.core.error_handler import ErrorHandler
from src.core.orchestrator import SyncOrchestrator
from src.core.localization import get_localization

# Настройка логирования в консоль
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Вывод в консоль
    ]
)

APP_NAME = 'FileSync'
# Используем папку проекта для хранения данных
PROJECT_DIR = Path(__file__).parent.parent.parent  # Корень проекта
LOGS_DIR = PROJECT_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = PROJECT_DIR / 'filesync.db'

db_manager = DatabaseManager(str(DB_PATH))
error_handler = ErrorHandler(app_name=APP_NAME, log_dir=str(LOGS_DIR))
orchestrator = SyncOrchestrator(db_manager, error_handler)

def get_target_options(loc):
    """Получить опции типов хранилищ на текущем языке"""
    return {
        'local': loc.get('target_local'),
        's3': loc.get('target_s3'),
        'ftp': loc.get('target_ftp'),
        'smb': loc.get('target_smb'),
        'gdrive': loc.get('target_gdrive'),
        'dropbox': loc.get('target_dropbox'),
    }

def get_config_columns(loc):
    """Получить колонки таблицы конфигураций на текущем языке"""
    return [
        {'name': 'id', 'label': loc.get('col_id'), 'field': 'id', 'sortable': True, 'align': 'left'},
        {'name': 'name', 'label': loc.get('col_name'), 'field': 'name', 'sortable': True, 'align': 'left'},
        {'name': 'source_path', 'label': loc.get('col_source'), 'field': 'source_path', 'sortable': True, 'align': 'left'},
        {'name': 'target', 'label': loc.get('col_target'), 'field': 'target', 'sortable': True, 'align': 'left'},
        {'name': 'status', 'label': loc.get('col_status'), 'field': 'status', 'sortable': True, 'align': 'center'},
    ]

def get_history_columns(loc):
    """Получить колонки таблицы истории на текущем языке"""
    return [
        {'name': 'id', 'label': loc.get('col_id'), 'field': 'id', 'sortable': True, 'align': 'left'},
        {'name': 'config', 'label': loc.get('col_config'), 'field': 'config', 'sortable': True, 'align': 'left'},
        {'name': 'status', 'label': loc.get('col_status'), 'field': 'status', 'sortable': True, 'align': 'center'},
        {'name': 'files_copied', 'label': 'Скопировано' if loc.get_language() == 'ru' else 'Copied', 'field': 'files_copied', 'sortable': True, 'align': 'right'},
        {'name': 'files_updated', 'label': 'Обновлено' if loc.get_language() == 'ru' else 'Updated', 'field': 'files_updated', 'sortable': True, 'align': 'right'},
        {'name': 'files_deleted', 'label': 'Удалено' if loc.get_language() == 'ru' else 'Deleted', 'field': 'files_deleted', 'sortable': True, 'align': 'right'},
        {'name': 'start_time', 'label': loc.get('col_start_time'), 'field': 'start_time', 'sortable': True, 'align': 'left'},
    ]


async def run_in_executor(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _select_folder_sync(title=None):
    """Synchronous folder selection - to be run in executor."""
    if title is None:
        title = loc.get('dialog_select_folder')
    root = Tk()
    root.withdraw()
    root.wm_attributes('-topmost', 1)
    folder = filedialog.askdirectory(title=title, parent=root)
    root.destroy()
    return folder


def _select_file_sync(title=None, filetypes=None):
    """Synchronous file selection - to be run in executor."""
    if title is None:
        title = loc.get('dialog_select_file')
    root = Tk()
    root.withdraw()
    root.wm_attributes('-topmost', 1)
    if filetypes is None:
        filetypes = [("All files", "*.*")]
    file = filedialog.askopenfilename(title=title, filetypes=filetypes, parent=root)
    root.destroy()
    return file


async def select_folder(title=None):
    """Async folder selection."""
    if title is None:
        title = loc.get('dialog_select_folder')
    return await run_in_executor(_select_folder_sync, title)


async def select_file(title=None, filetypes=None):
    """Async file selection."""
    if title is None:
        title = loc.get('dialog_select_file')
    return await run_in_executor(_select_file_sync, title, filetypes)


def load_user_language():
    """Загрузить язык пользователя из файла настроек"""
    lang_file = PROJECT_DIR / 'ui_language.txt'
    if lang_file.exists():
        try:
            lang = lang_file.read_text(encoding='utf-8').strip()
            if lang in ['ru', 'en']:
                return lang
        except Exception:
            pass
    return None

def save_user_language(language):
    """Сохранить язык пользователя в файл настроек"""
    lang_file = PROJECT_DIR / 'ui_language.txt'
    try:
        lang_file.write_text(language, encoding='utf-8')
        print(f"DEBUG: Language '{language}' saved to {lang_file}")
    except Exception as e:
        print(f"ERROR: Failed to save language: {e}")

@ui.page('/')
def create_ui() -> None:
    # Создаем экземпляр локализации для этого пользователя
    from src.core.constants import DEFAULT_LANGUAGE

    # Восстанавливаем язык из файла настроек
    stored_lang = load_user_language()

    if not stored_lang or stored_lang not in ['ru', 'en']:
        stored_lang = DEFAULT_LANGUAGE

    print(f"DEBUG: Stored language from file: {stored_lang}")

    # Создаем локализацию с выбранным языком
    loc = get_localization(stored_lang)
    print(f"DEBUG: Language loaded: {loc.get_language()}")

    # Получаем переводы для текущего языка
    TARGET_OPTIONS = get_target_options(loc)
    CONFIG_COLUMNS = get_config_columns(loc)
    HISTORY_COLUMNS = get_history_columns(loc)

    history_refresh_ref = {'func': lambda: None}
    ui_refs = {'header_title': None, 'header_subtitle': None, 'refresh_btn': None, 'language_select': None}

    def toggle_language():
        """Переключить язык интерфейса"""
        current = loc.get_language()
        new_lang = 'en' if current == 'ru' else 'ru'
        print(f"DEBUG: Toggling language from {current} to {new_lang}")

        # Сохраняем язык в файл
        save_user_language(new_lang)

        # Показываем уведомление и перезагружаем страницу
        ui.notify(f'Switching to {new_lang.upper()}...', type='info', position='top')

        # Перезагружаем через JavaScript
        ui.run_javascript('setTimeout(() => window.location.reload(), 500);', timeout=5.0)

        print(f"DEBUG: Language '{new_lang}' saved, reloading page...")

    # Заголовок
    with ui.header().classes('bg-gradient-to-r from-blue-600 to-blue-800 text-white justify-between items-center px-6 py-4 shadow-lg'):
        with ui.row().classes('items-center gap-3'):
            ui.icon('backup', size='36px')
            with ui.column().classes('gap-0'):
                ui_refs['header_title'] = ui.label(loc.get('app_name')).classes('text-3xl font-bold')
                ui_refs['header_subtitle'] = ui.label(loc.get('app_subtitle')).classes('text-sm opacity-90')
        with ui.row().classes('gap-2 items-center'):
            # Кнопка переключения языка
            current_lang = loc.get_language()
            lang_icon = '🇬🇧 EN' if current_lang == 'ru' else '🇷🇺 RU'
            lang_tooltip = 'Switch to English' if current_lang == 'ru' else 'Переключить на русский'
            ui.button(lang_icon, on_click=toggle_language).props('flat color=white').classes('text-lg').tooltip(lang_tooltip)

            ui_refs['refresh_btn'] = ui.button(loc.get('btn_refresh_services'), on_click=lambda: orchestrator.reload_configuration(initial_sync=False)).props('flat color=white outline')
            ui.label(loc.get('version')).classes('text-xs opacity-75 px-2')

    # Навигация
    with ui.tabs().classes('w-full bg-white shadow-md') as tabs:
        configs_tab = ui.tab(loc.get('tab_configs'))
        history_tab = ui.tab(loc.get('tab_history'))
        logs_tab = ui.tab(loc.get('tab_logs'))
        status_tab = ui.tab(loc.get('tab_status'))

    with ui.tab_panels(tabs, value=configs_tab).classes('w-full p-6 bg-gray-50'):
        # ========== ВКЛАДКА КОНФИГУРАЦИИ ==========
        with ui.tab_panel(configs_tab):
            with ui.card().classes('w-full shadow-xl'):
                with ui.row().classes('justify-between items-center w-full mb-4'):
                    ui.label(loc.get('config_title')).classes('text-2xl font-bold text-gray-800')
                    ui.button(loc.get('btn_add'), on_click=lambda: open_config_dialog(), icon='add').props('color=primary size=lg')

                config_table = ui.table(columns=CONFIG_COLUMNS, rows=[], row_key='id', selection='single').classes('w-full')
                config_table.props('flat bordered')

                def refresh_configs() -> None:
                    selected_id = config_table.selected[0]['id'] if config_table.selected else None
                    configs = db_manager.get_all_sync_configs()
                    rows: List[Dict[str, Any]] = []
                    for cfg in configs:
                        is_active = cfg.get('is_active', True)
                        has_realtime = cfg.get('realtime_monitor', False)

                        status_parts = []
                        if is_active:
                            status_parts.append(loc.get('status_active'))
                        else:
                            status_parts.append(loc.get('status_inactive'))

                        if has_realtime:
                            status_parts.append(loc.get('status_monitoring'))

                        rows.append({
                            'id': cfg['id'],
                            'name': cfg['name'],
                            'source_path': cfg['source_path'],
                            'target': TARGET_OPTIONS.get(cfg['target_type'], cfg['target_type']),
                            'status': ' | '.join(status_parts),
                        })
                    config_table.rows = rows
                    if selected_id is not None:
                        matching_rows = [row for row in rows if row['id'] == selected_id]
                        if matching_rows:
                            config_table.selected = matching_rows

                def get_selected_config() -> Optional[Dict[str, Any]]:
                    if not config_table.selected:
                        ui.notify(loc.get('notify_select_config'), type='warning')
                        return None
                    row = config_table.selected[0]
                    cfg = next((c for c in db_manager.get_all_sync_configs() if c['id'] == row['id']), None)
                    if not cfg:
                        ui.notify(loc.get('notify_config_not_found'), type='warning')
                    return cfg

                async def manual_sync_selected() -> None:
                    cfg = get_selected_config()
                    if not cfg:
                        return
                    config_id = cfg['id']
                    ui.notify(f'{loc.get("notify_sync_start")}: {cfg["name"]}', type='info')
                    success = await run_in_executor(orchestrator.trigger_sync, config_id)
                    if success:
                        ui.notify(loc.get('notify_sync_success'), type='positive')
                    else:
                        ui.notify(loc.get('notify_sync_error'), type='negative')
                    history_refresh_ref['func']()

                async def toggle_config_status() -> None:
                    cfg = get_selected_config()
                    if not cfg:
                        return
                    new_status = not cfg.get('is_active', True)
                    await run_in_executor(db_manager.update_sync_config, cfg['id'], is_active=new_status)
                    orchestrator.reload_configuration(initial_sync=False)
                    refresh_configs()
                    status_text = loc.get('notify_config_activated') if new_status else loc.get('notify_config_deactivated')
                    ui.notify(status_text, type='positive')

                async def delete_selected_config() -> None:
                    cfg = get_selected_config()
                    if not cfg:
                        return
                    confirm_msg = loc.get('dialog_delete_confirm').format(cfg["name"])
                    result = await ui.run_javascript(f'confirm("{confirm_msg}")')
                    if not result:
                        return
                    await run_in_executor(db_manager.delete_sync_config, cfg['id'])
                    orchestrator.reload_configuration(initial_sync=False)
                    refresh_configs()
                    ui.notify(loc.get('notify_config_deleted'), type='positive')

                def edit_selected() -> None:
                    cfg = get_selected_config()
                    if cfg:
                        open_config_dialog(cfg)

                def open_config_dialog(config: Optional[Dict[str, Any]] = None) -> None:
                    is_edit = config is not None
                    config_id = config.get('id') if config else None

                    # Данные конфигурации
                    config_data = {
                        'name': config.get('name', '') if config else '',
                        'description': config.get('description', '') if config else '',
                        'source_path': config.get('source_path', '') if config else '',
                        'target_type': config.get('target_type', 'local') if config else 'local',
                        'target_path': config.get('target_path', '') if config else '',
                        'target_settings': config.get('target_settings', {}) if config else {},
                        'realtime_monitor': config.get('realtime_monitor', False) if config else False,
                        'delete_missing': config.get('delete_missing', False) if config else False,
                        'is_active': config.get('is_active', True) if config else True,
                    }

                    dialog = ui.dialog().props('maximized')
                    test_result_label = None

                    with dialog, ui.card().classes('w-full h-full'):
                        # Заголовок
                        with ui.row().classes('w-full justify-between items-center mb-4 pb-4 border-b'):
                            ui.label('✏️ Редактирование конфигурации' if is_edit else '➕ Новая конфигурация синхронизации').classes('text-2xl font-bold')
                            ui.button(icon='close', on_click=dialog.close).props('flat round')

                        with ui.scroll_area().classes('w-full flex-grow'):
                            with ui.column().classes('w-full max-w-4xl mx-auto gap-6'):
                                # Основная информация
                                with ui.card().classes('w-full'):
                                    ui.label('📝 Основная информация').classes('text-lg font-semibold mb-3')

                                    name_input = ui.input('Название конфигурации', value=config_data['name']).props('outlined dense').classes('w-full')
                                    name_input.props('hint="Например: Документы на R2" prefix-icon=label')

                                    description_input = ui.textarea('Описание (необязательно)', value=config_data['description']).props('outlined rows=2').classes('w-full')

                                # Источник
                                with ui.card().classes('w-full'):
                                    ui.label('📂 Источник синхронизации').classes('text-lg font-semibold mb-3')

                                    with ui.row().classes('w-full gap-2'):
                                        source_input = ui.input('Путь к папке', value=config_data['source_path']).props('outlined dense').classes('flex-grow')
                                        source_input.props('hint="Локальная папка для синхронизации" prefix-icon=folder')

                                        async def browse_source():
                                            folder = await select_folder("Выберите папку для синхронизации")
                                            if folder:
                                                source_input.value = folder
                                                source_input.update()

                                        ui.button('📁 Обзор', on_click=browse_source).props('outline')

                                # Назначение
                                with ui.card().classes('w-full'):
                                    ui.label('🎯 Назначение').classes('text-lg font-semibold mb-3')

                                    target_type_select = ui.select(
                                        options=TARGET_OPTIONS,
                                        value=config_data['target_type'],
                                        label='Тип хранилища'
                                    ).props('outlined dense').classes('w-full')

                                    target_settings_container = ui.column().classes('w-full gap-3 mt-4')
                                    test_button_container = ui.row().classes('w-full mt-4')

                                    # Храним ссылки на поля ввода для каждого типа
                                    fields_refs = {}

                                    def update_target_settings():
                                        target_settings_container.clear()
                                        test_button_container.clear()
                                        fields_refs.clear()
                                        target_type = target_type_select.value
                                        settings = config_data.get('target_settings', {})

                                        with target_settings_container:
                                            # === ЛОКАЛЬНАЯ ПАПКА ===
                                            if target_type == 'local':
                                                with ui.row().classes('w-full gap-2'):
                                                    target_path_input = ui.input('Целевая папка', value=config_data.get('target_path', '')).props('outlined dense').classes('flex-grow')
                                                    target_path_input.props('hint="Папка назначения" prefix-icon=folder_open')
                                                    fields_refs['path'] = target_path_input

                                                    async def browse_target():
                                                        folder = await select_folder("Выберите целевую папку")
                                                        if folder:
                                                            target_path_input.value = folder
                                                            target_path_input.update()

                                                    ui.button('📁 Обзор', on_click=browse_target).props('outline')

                                            # === S3 / R2 ===
                                            elif target_type == 's3':
                                                ui.label('🔑 Настройки подключения S3 / Cloudflare R2').classes('font-semibold text-sm text-gray-600')

                                                fields_refs['endpoint'] = ui.input('Endpoint URL', value=settings.get('endpoint', '')).props('outlined dense').classes('w-full')
                                                fields_refs['endpoint'].props('hint="Например: https://your-account-id.r2.cloudflarestorage.com" prefix-icon=link')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['access_key'] = ui.input('Access Key', value=settings.get('access_key', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['secret_key'] = ui.input('Secret Key', value=settings.get('secret_key', ''), password=True, password_toggle_button=True).props('outlined dense').classes('flex-1')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['bucket'] = ui.input('Bucket Name', value=settings.get('bucket', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['bucket'].props('hint="Имя bucket" prefix-icon=inventory_2')

                                                    fields_refs['region'] = ui.input('Region', value=settings.get('region', 'auto')).props('outlined dense').classes('flex-1')
                                                    fields_refs['region'].props('hint="Регион (auto для R2)" prefix-icon=public')

                                                fields_refs['prefix'] = ui.input('Prefix (необязательно)', value=settings.get('prefix', '')).props('outlined dense').classes('w-full')
                                                fields_refs['prefix'].props('hint="Префикс пути в bucket, например: backups/documents/" prefix-icon=folder_special')

                                            # === FTP ===
                                            elif target_type == 'ftp':
                                                ui.label('🌐 Настройки FTP-сервера').classes('font-semibold text-sm text-gray-600')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['server'] = ui.input('Сервер', value=settings.get('server', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['server'].props('hint="IP или домен" prefix-icon=dns')

                                                    fields_refs['port'] = ui.number('Порт', value=settings.get('port', 21), min=1, max=65535).props('outlined dense').classes('w-32')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['username'] = ui.input('Логин', value=settings.get('username', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['password'] = ui.input('Пароль', value=settings.get('password', ''), password=True, password_toggle_button=True).props('outlined dense').classes('flex-1')

                                                fields_refs['folder'] = ui.input('Папка на сервере', value=settings.get('folder', '/')).props('outlined dense').classes('w-full')
                                                fields_refs['folder'].props('hint="Путь на FTP-сервере" prefix-icon=folder')

                                                fields_refs['use_ssl'] = ui.checkbox('Использовать FTPS (SSL/TLS)', value=settings.get('use_ssl', False))

                                            # === SMB ===
                                            elif target_type == 'smb':
                                                ui.label('💻 Настройки SMB/CIFS (сетевая папка)').classes('font-semibold text-sm text-gray-600')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['server'] = ui.input('Сервер', value=settings.get('server', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['server'].props('hint="IP или имя сервера" prefix-icon=computer')

                                                    fields_refs['port'] = ui.number('Порт', value=settings.get('port', 445), min=1, max=65535).props('outlined dense').classes('w-32')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['username'] = ui.input('Логин', value=settings.get('username', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['password'] = ui.input('Пароль', value=settings.get('password', ''), password=True, password_toggle_button=True).props('outlined dense').classes('flex-1')

                                                fields_refs['domain'] = ui.input('Домен (необязательно)', value=settings.get('domain', '')).props('outlined dense').classes('w-full')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['share'] = ui.input('Сетевая папка (Share)', value=settings.get('share', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['share'].props('hint="Имя сетевой папки" prefix-icon=share')

                                                    fields_refs['path'] = ui.input('Путь внутри Share', value=settings.get('path', '')).props('outlined dense').classes('flex-1')
                                                    fields_refs['path'].props('hint="Подпапка внутри сетевой папки" prefix-icon=folder')

                                            # === GOOGLE DRIVE ===
                                            elif target_type == 'gdrive':
                                                ui.label('☁️ Настройки Google Drive').classes('font-semibold text-sm text-gray-600')

                                                with ui.row().classes('w-full gap-2'):
                                                    fields_refs['credentials_file'] = ui.input('Файл учетных данных (credentials.json)', value=settings.get('credentials_file', '')).props('outlined dense').classes('flex-grow')
                                                    fields_refs['credentials_file'].props('hint="OAuth2 credentials из Google Cloud Console" prefix-icon=key')

                                                    async def browse_credentials():
                                                        file = await select_file("Выберите credentials.json", [("JSON files", "*.json"), ("All files", "*.*")])
                                                        if file:
                                                            fields_refs['credentials_file'].value = file
                                                            fields_refs['credentials_file'].update()

                                                    ui.button('📄 Обзор', on_click=browse_credentials).props('outline')

                                                fields_refs['folder'] = ui.input('Папка в Google Drive', value=settings.get('folder', '/')).props('outlined dense').classes('w-full')
                                                fields_refs['folder'].props('hint="ID папки или \'/\' для корня" prefix-icon=folder')

                                            # === DROPBOX ===
                                            elif target_type == 'dropbox':
                                                ui.label('📦 Настройки Dropbox').classes('font-semibold text-sm text-gray-600')

                                                fields_refs['token'] = ui.input('Access Token', value=settings.get('token', ''), password=True, password_toggle_button=True).props('outlined dense').classes('w-full')
                                                fields_refs['token'].props('hint="Токен доступа из https://www.dropbox.com/developers" prefix-icon=vpn_key')

                                                fields_refs['folder'] = ui.input('Папка в Dropbox', value=settings.get('folder', '/')).props('outlined dense').classes('w-full')
                                                fields_refs['folder'].props('hint="Путь к папке в Dropbox" prefix-icon=folder')

                                        # Кнопка тестирования
                                        with test_button_container:
                                            nonlocal test_result_label

                                            async def test_connection():
                                                target_type = target_type_select.value

                                                # Собираем настройки из полей
                                                settings = {}
                                                if target_type == 'local':
                                                    settings['path'] = fields_refs.get('path', ui.input('')).value
                                                else:
                                                    for key, field in fields_refs.items():
                                                        if hasattr(field, 'value'):
                                                            settings[key] = field.value

                                                ui.notify('🔄 Тестирование подключения...', type='info')
                                                result = await run_in_executor(orchestrator.sync_service.test_connection, target_type, settings)

                                                if result['success']:
                                                    ui.notify(f"✅ {result['message']}", type='positive', timeout=5000)
                                                    if test_result_label:
                                                        test_result_label.set_text(f"✅ {result['message']}")
                                                        test_result_label.classes('text-green-600', remove='text-red-600')
                                                else:
                                                    ui.notify(f"❌ {result['message']}", type='negative', timeout=5000)
                                                    if test_result_label:
                                                        test_result_label.set_text(f"❌ {result['message']}")
                                                        test_result_label.classes('text-red-600', remove='text-green-600')

                                            ui.button('🔌 Тестировать подключение', on_click=test_connection, icon='check_circle').props('color=primary outline')
                                            test_result_label = ui.label('').classes('text-sm font-medium ml-4')

                                    target_type_select.on_value_change(lambda: update_target_settings())
                                    update_target_settings()

                                # Дополнительные параметры
                                with ui.card().classes('w-full'):
                                    ui.label('⚙️ Дополнительные параметры').classes('text-lg font-semibold mb-3')

                                    with ui.row().classes('w-full gap-6'):
                                        realtime_checkbox = ui.checkbox('👁️ Мониторинг в реальном времени', value=config_data['realtime_monitor'])
                                        realtime_checkbox.props('hint="Автоматическая синхронизация при изменении файлов"')

                                        delete_checkbox = ui.checkbox('🗑️ Удалять отсутствующие файлы', value=config_data['delete_missing'])
                                        delete_checkbox.props('hint="Удалять файлы в назначении, которых нет в источнике"')

                                        active_checkbox = ui.checkbox('✅ Конфигурация активна', value=config_data['is_active'])

                        # Кнопки действий
                        with ui.row().classes('w-full justify-end gap-2 mt-4 pt-4 border-t'):
                            ui.button('❌ Отмена', on_click=dialog.close).props('outline size=lg')

                            async def save_config():
                                try:
                                    if not name_input.value.strip():
                                        ui.notify('⚠️ Укажите название конфигурации', type='warning')
                                        return
                                    if not source_input.value.strip():
                                        ui.notify('⚠️ Укажите папку для синхронизации', type='warning')
                                        return

                                    target_type = target_type_select.value

                                    # Собираем настройки
                                    target_settings = {}
                                    target_path = ''

                                    if target_type == 'local':
                                        target_path = fields_refs.get('path', ui.input('')).value
                                        if not target_path:
                                            ui.notify('⚠️ Укажите целевую папку', type='warning')
                                            return
                                    else:
                                        for key, field in fields_refs.items():
                                            if hasattr(field, 'value'):
                                                target_settings[key] = field.value

                                    payload = {
                                        'name': name_input.value.strip(),
                                        'description': description_input.value.strip(),
                                        'source_path': source_input.value.strip(),
                                        'target_type': target_type,
                                        'target_path': target_path,
                                        'target_settings': target_settings,
                                        'sync_type': 'one_way',
                                        'delete_missing': delete_checkbox.value,
                                        'realtime_monitor': realtime_checkbox.value,
                                        'is_active': active_checkbox.value,
                                    }

                                    if is_edit:
                                        await run_in_executor(db_manager.update_sync_config, config_id, **payload)
                                        ui.notify('✅ Конфигурация обновлена', type='positive')
                                    else:
                                        await run_in_executor(db_manager.add_sync_config, **payload)
                                        ui.notify('✅ Конфигурация добавлена', type='positive')

                                    orchestrator.reload_configuration(initial_sync=False)
                                    refresh_configs()
                                    dialog.close()
                                except Exception as exc:
                                    error_handler.log_error(f'Ошибка при сохранении конфигурации: {exc}')
                                    ui.notify(f'❌ Ошибка: {exc}', type='negative')

                            ui.button('💾 Сохранить', on_click=save_config).props('color=primary size=lg')

                    dialog.open()

                # Панель управления
                with ui.row().classes('gap-3 mt-6 p-4 bg-gray-50 rounded-lg'):
                    sync_btn = ui.button(loc.get('btn_sync'), on_click=manual_sync_selected, icon='sync').props('color=green size=md')
                    edit_btn = ui.button(loc.get('btn_edit'), on_click=edit_selected, icon='edit').props('color=blue size=md')
                    toggle_btn = ui.button(loc.get('btn_toggle'), on_click=toggle_config_status, icon='power_settings_new').props('size=md')
                    delete_btn = ui.button(loc.get('btn_delete'), on_click=delete_selected_config, icon='delete').props('color=red size=md')
                    ui.space()
                    ui.button(loc.get('btn_refresh_list'), on_click=refresh_configs, icon='refresh').props('outline size=md')

                # Обновление состояния кнопок при изменении выбора
                def update_buttons():
                    has_selection = len(config_table.selected) > 0
                    sync_btn.enabled = has_selection
                    edit_btn.enabled = has_selection
                    toggle_btn.enabled = has_selection
                    delete_btn.enabled = has_selection

                config_table.on('update:selected', lambda: update_buttons())
                update_buttons()  # Начальное состояние

                refresh_configs()
                ui.timer(10, refresh_configs)

        # ========== ВКЛАДКА ИСТОРИЯ ==========
        with ui.tab_panel(history_tab):
            with ui.card().classes('w-full shadow-xl'):
                ui.label(loc.get('history_title')).classes('text-2xl font-bold mb-4')

                with ui.row().classes('gap-4 mb-4 items-center'):
                    ui.label(loc.get('history_period')).classes('font-semibold')
                    history_days_slider = ui.slider(min=1, max=30, value=7, step=1).props('label-always').classes('flex-1 max-w-md')
                    ui.label().bind_text_from(history_days_slider, 'value', lambda v: f'{int(v)} {loc.get("history_days")}').classes('font-semibold')
                    ui.button(loc.get('btn_refresh'), on_click=lambda: history_refresh_ref['func'](), icon='refresh').props('outline')

                history_table = ui.table(columns=HISTORY_COLUMNS, rows=[], row_key='id', selection='single').classes('w-full')
                history_table.props('flat bordered dense')

                # Добавляем шаблон для расширяемых строк с деталями файлов
                history_table.add_slot('body', r'''
                    <q-tr :props="props" @click="props.selected = !props.selected" :class="props.selected ? 'bg-blue-100' : ''" style="cursor: pointer;">
                        <q-td v-for="col in props.cols" :key="col.name" :props="props">
                            {{ col.value }}
                        </q-td>
                    </q-tr>
                    <q-tr v-if="props.row._file_ops && props.row._file_ops.length > 0" :props="props">
                        <q-td colspan="100%">
                            <div class="text-left" style="padding: 10px; background: #f5f5f5; font-size: 12px;">
                                <details>
                                    <summary style="cursor: pointer; font-weight: bold; margin-bottom: 5px;">
                                        📋 Детали операций ({{ props.row._file_ops.length }} файлов)
                                    </summary>
                                    <div v-for="op in props.row._file_ops.slice(0, 50)" :key="op.id" style="padding: 3px 0; border-bottom: 1px solid #e0e0e0;">
                                        <span v-if="op.operation_type === 'copied'">📋</span>
                                        <span v-else-if="op.operation_type === 'updated'">🔄</span>
                                        <span v-else-if="op.operation_type === 'deleted'">🗑️</span>
                                        <strong>{{ op.operation_type }}</strong>:
                                        <code style="background: #fff; padding: 2px 5px;">{{ op.file_path }}</code>
                                        <span v-if="op.source_path"> → <code style="background: #fff; padding: 2px 5px;">{{ op.target_path }}</code></span>
                                        <span v-if="op.file_size > 0" style="color: #666;"> ({{ (op.file_size / 1024 / 1024).toFixed(2) }} MB)</span>
                                    </div>
                                    <div v-if="props.row._file_ops.length > 50" style="margin-top: 5px; color: #666; font-style: italic;">
                                        ... и ещё {{ props.row._file_ops.length - 50 }} файлов
                                    </div>
                                </details>
                            </div>
                        </q-td>
                    </q-tr>
                ''')

                def show_history_details():
                    """Показать детали выбранной синхронизации"""
                    if not history_table.selected:
                        ui.notify(loc.get('notify_select_history') if hasattr(loc, 'notify_select_history') else 'Выберите запись в истории', type='warning')
                        return

                    history_id = history_table.selected[0]['id']
                    history_record = db_manager.get_sync_history_record(history_id)

                    if not history_record:
                        ui.notify('История не найдена', type='warning')
                        return

                    # Получаем конфигурацию для отображения путей
                    config = db_manager.get_sync_config(history_record['config_id'])

                    # Получаем список операций с файлами
                    file_operations = db_manager.get_file_operations(history_id)

                    with ui.dialog() as details_dialog, ui.card().classes('w-full max-w-6xl'):
                        with ui.row().classes('w-full justify-between items-center mb-4 pb-4 border-b'):
                            ui.label(f'📊 Детали синхронизации #{history_id}').classes('text-2xl font-bold')
                            ui.button(icon='close', on_click=details_dialog.close).props('flat round')

                        with ui.scroll_area().classes('w-full h-96'):
                            with ui.column().classes('w-full gap-4'):
                                # Информация о путях
                                if config:
                                    with ui.card().classes('w-full'):
                                        ui.label('📂 Пути синхронизации').classes('text-lg font-semibold mb-2')
                                        with ui.column().classes('gap-2'):
                                            ui.label('Источник:').classes('font-semibold')
                                            ui.label(config.get('source_path', 'N/A')).classes('text-sm font-mono bg-gray-100 p-2 rounded')

                                            ui.label('Назначение:').classes('font-semibold')
                                            target_path = config.get('target_path') or config.get('target_settings', {}).get('path', 'N/A')
                                            ui.label(f"{config.get('target_type', 'N/A')}: {target_path}").classes('text-sm font-mono bg-gray-100 p-2 rounded')

                                # Общая информация
                                with ui.card().classes('w-full'):
                                    ui.label('📝 Общая информация').classes('text-lg font-semibold mb-2')
                                    with ui.grid(columns=2).classes('gap-2'):
                                        ui.label('Статус:').classes('font-semibold')
                                        status_icon = '✅' if history_record['status'] == 'completed' else '❌' if history_record['status'] == 'failed' else '🔄'
                                        ui.label(f"{status_icon} {history_record['status']}")

                                        ui.label('Начало:').classes('font-semibold')
                                        ui.label(history_record.get('start_time', '')[:19] if history_record.get('start_time') else 'N/A')

                                        ui.label('Окончание:').classes('font-semibold')
                                        ui.label(history_record.get('end_time', '')[:19] if history_record.get('end_time') else 'N/A')

                                        ui.label('Скопировано файлов:').classes('font-semibold')
                                        ui.label(str(history_record.get('files_copied', 0)))

                                        ui.label('Обновлено файлов:').classes('font-semibold')
                                        ui.label(str(history_record.get('files_updated', 0)))

                                        ui.label('Удалено файлов:').classes('font-semibold')
                                        ui.label(str(history_record.get('files_deleted', 0)))

                                        ui.label('Ошибок:').classes('font-semibold')
                                        ui.label(str(history_record.get('errors', 0)))

                                    if history_record.get('message'):
                                        ui.separator()
                                        ui.label('Сообщение:').classes('font-semibold')
                                        ui.label(history_record['message']).classes('text-sm')

                                # Список операций с файлами
                                if file_operations:
                                    with ui.card().classes('w-full'):
                                        ui.label(f'📁 Операции с файлами ({len(file_operations)})').classes('text-lg font-semibold mb-2')

                                        file_ops_columns = [
                                            {'name': 'operation', 'label': 'Операция', 'field': 'operation', 'sortable': True, 'align': 'left'},
                                            {'name': 'file_path', 'label': 'Файл', 'field': 'file_path', 'sortable': True, 'align': 'left'},
                                            {'name': 'size', 'label': 'Размер', 'field': 'size', 'sortable': True, 'align': 'right'},
                                            {'name': 'status', 'label': 'Статус', 'field': 'status', 'sortable': True, 'align': 'center'},
                                        ]

                                        file_ops_rows = []
                                        for op in file_operations:
                                            op_icon = '📋' if op['operation_type'] == 'copied' else '🔄' if op['operation_type'] == 'updated' else '🗑️'
                                            status_icon = '✅' if op['status'] == 'success' else '❌'
                                            size_mb = op.get('file_size', 0) / (1024 * 1024) if op.get('file_size', 0) > 0 else 0

                                            file_ops_rows.append({
                                                'operation': f"{op_icon} {op['operation_type']}",
                                                'file_path': op['file_path'],
                                                'size': f"{size_mb:.2f} MB" if size_mb > 0 else '0 MB',
                                                'status': f"{status_icon} {op['status']}",
                                            })

                                        ui.table(columns=file_ops_columns, rows=file_ops_rows, row_key='file_path').classes('w-full').props('dense')
                                else:
                                    ui.label('Нет детальной информации об операциях с файлами').classes('text-gray-500 italic')

                    details_dialog.open()

                def refresh_history():
                    days = int(history_days_slider.value or 7)
                    history = db_manager.get_recent_sync_history(days=days, limit=200)
                    configs_map = {cfg['id']: cfg['name'] for cfg in db_manager.get_all_sync_configs()}
                    rows = []
                    for record in history:
                        status_icon = '✅' if record['status'] == 'completed' else '❌' if record['status'] == 'failed' else '🔄'

                        # Получаем список файлов для этой синхронизации
                        file_ops = db_manager.get_file_operations(record['id'])

                        rows.append({
                            'id': record['id'],
                            'config': configs_map.get(record['config_id'], f"ID: {record['config_id']}"),
                            'status': f"{status_icon} {record['status']}",
                            'files_copied': record.get('files_copied', 0),
                            'files_updated': record.get('files_updated', 0),
                            'files_deleted': record.get('files_deleted', 0),
                            'start_time': record.get('start_time', '')[:19] if record.get('start_time') else '',
                            '_file_ops': file_ops  # Скрытое поле для диалога
                        })
                    history_table.rows = rows

                # Кнопка для просмотра деталей
                with ui.row().classes('gap-3 mt-4'):
                    ui.button('🔍 Показать детали', on_click=show_history_details, icon='info').props('color=primary')

                history_refresh_ref['func'] = refresh_history
                refresh_history()
                ui.timer(15, refresh_history)

        # ========== ВКЛАДКА ЖУРНАЛЫ ==========
        with ui.tab_panel(logs_tab):
            with ui.card().classes('w-full shadow-xl'):
                ui.label(loc.get('logs_title')).classes('text-2xl font-bold mb-4')

                logs_dir = LOGS_DIR
                log_files = sorted(logs_dir.glob('*.log'), reverse=True) if logs_dir.exists() else []

                log_select = ui.select(
                    options={str(p): p.name for p in log_files},
                    label=loc.get('logs_select'),
                    value=str(log_files[0]) if log_files else None
                ).props('outlined').classes('w-full mb-4')

                log_area = ui.textarea(loc.get('logs_content')).props('outlined rows=30').classes('w-full font-mono text-xs')
                log_area.props('readonly')

                def refresh_logs():
                    selected = log_select.value
                    if not selected:
                        log_area.value = loc.get('logs_no_file')
                        return
                    path = Path(selected)
                    try:
                        content = path.read_text(encoding='utf-8')
                        lines = content.splitlines()
                        log_area.value = '\n'.join(lines[-1000:])
                    except Exception as exc:
                        log_area.value = f'{loc.get("logs_error")}: {exc}'

                # Автоматическое обновление при смене файла
                log_select.on('update:model-value', lambda: refresh_logs())

                ui.button(loc.get('btn_refresh'), on_click=refresh_logs, icon='refresh').props('outline')
                if log_files:
                    refresh_logs()

        # ========== ВКЛАДКА СЛУЖБЫ ==========
        with ui.tab_panel(status_tab):
            with ui.card().classes('w-full shadow-xl'):
                ui.label(loc.get('services_title')).classes('text-2xl font-bold mb-4')

                status_container = ui.column().classes('w-full gap-4')

                def refresh_status():
                    status_container.clear()

                    with status_container:
                        with ui.card().classes('w-full'):
                            ui.label(loc.get('services_active')).classes('text-lg font-semibold mb-2')
                            tasks = orchestrator.active_tasks()
                            if tasks:
                                for cfg_id, task in tasks.items():
                                    ui.label(f"• {loc.get('col_config')} {cfg_id}: {task.get('status')} - {task.get('message', '')}")
                            else:
                                ui.label(loc.get('services_no_tasks')).classes('text-gray-500')

                        with ui.card().classes('w-full'):
                            ui.label(loc.get('services_monitoring')).classes('text-lg font-semibold mb-2')
                            monitored = orchestrator.monitored_paths()
                            if monitored:
                                for path in monitored:
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('folder', size='sm').classes('text-blue-600')
                                        ui.label(path).classes('font-mono text-sm')
                            else:
                                ui.label(loc.get('services_no_monitoring')).classes('text-gray-500')

                refresh_status()
                ui.timer(10, refresh_status)

    # Футер
    with ui.footer().classes('bg-gradient-to-r from-gray-100 to-gray-200 justify-between text-sm text-gray-700 px-6 py-3 shadow-lg'):
        ui.label(f'📁 {loc.get("database")}: {DB_PATH}').classes('font-mono text-xs')
        ui.label(loc.get('copyright')).classes('font-semibold')


def main() -> None:
    orchestrator.start()

    @app.on_shutdown
    def _shutdown() -> None:
        orchestrator.stop()

    ui.run(
        title='FileSync',
        host='0.0.0.0',
        port=8081,
        show=True,
        reload=False,
        favicon='🔄',
        storage_secret='filesync-secret-key-change-in-production'
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
