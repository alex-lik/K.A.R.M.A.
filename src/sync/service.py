import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from src.core.database import DatabaseManager
from src.core.encryption import EncryptionManager
from src.core.error_handler import ErrorHandler
from src.sync.local import LocalSyncManager
from src.sync.gdrive import GoogleDriveSyncManager
from src.sync.ftp import FTPSyncManager
from src.sync.smb import SMBSyncManager
from src.sync.s3 import S3SyncManager
from src.sync.dropbox import DropboxSyncManager

logger = logging.getLogger(__name__)


class SyncService:
    """High-level orchestration of individual synchronisation engines."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        error_handler: ErrorHandler,
        encryption_manager: Optional[EncryptionManager] = None,
    ) -> None:
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.encryption_manager = encryption_manager or EncryptionManager()

        self.sync_managers = {
            'local': LocalSyncManager(db_manager, error_handler),
            'gdrive': GoogleDriveSyncManager(db_manager, error_handler),
            'ftp': FTPSyncManager(db_manager, error_handler),
            'smb': SMBSyncManager(db_manager, error_handler),
            's3': S3SyncManager(db_manager, error_handler),
            'dropbox': DropboxSyncManager(db_manager, error_handler),
        }

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def sync_config(
        self,
        config_id: int,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> bool:
        """Synchronise a configuration across the selected backend."""
        config = self.db_manager.get_sync_config(config_id)
        if not config:
            self.error_handler.log_error(f"Не найдена конфигурация с ID {config_id}")
            return False

        logger.info("Запуск синхронизации конфигурации %s -> %s", config['source_path'], config['target_type'])

        history_id = self.db_manager.add_sync_history(
            config_id=config_id,
            status='running',
            message='Запуск синхронизации',
            start_time=datetime.utcnow(),
        )

        def emit(message: str, level: str = 'info') -> None:
            if progress_callback:
                progress_callback(message, level)
            if level == 'error':
                logger.error(message)
            elif level == 'warning':
                logger.warning(message)
            else:
                logger.info(message)

        try:
            target_type = config['target_type']
            target_settings = config.get('target_settings') or {}
            filter_settings = config.get('filter_settings') or {}
            # По умолчанию включаем удаление отсутствующих файлов для корректной синхронизации
            delete_mode = bool(config.get('delete_missing', True))
            source_path = config['source_path']

            success = False
            result = {}

            if target_type == 'local':
                target_path = target_settings.get('path') or config.get('target_path')
                if not target_path:
                    raise ValueError('Целевая папка не указана для локальной синхронизации')
                emit(f"Локальная синхронизация: {source_path} -> {target_path}")
                result = self.sync_managers['local'].sync_folders(
                    config_id,
                    source_path,
                    target_path,
                    callback=lambda msg, *_: emit(msg),
                    delete_mode=delete_mode,
                    history_id=history_id,
                )
                success = result.get('errors', 0) == 0
                self.sync_managers['local'].update_file_states(config_id, source_path)

            elif target_type == 'gdrive':
                credentials_file = target_settings.get('credentials_file')
                folder_path = target_settings.get('folder', '/')
                convert_docs = bool(target_settings.get('convert_docs', False))
                ignore_google_files = bool(target_settings.get('ignore_google_files', True))

                if not credentials_file:
                    raise ValueError('Не указан файл учетных данных для Google Drive')

                manager = self.sync_managers['gdrive']
                if manager.authenticate(credentials_file):
                    try:
                        folder_id = manager.get_folder_id(folder_path)
                        result = manager.sync_folders(
                            config_id,
                            source_path,
                            folder_id,
                            callback=lambda msg, *_: emit(msg),
                            direction=target_settings.get('direction', 'upload'),
                            delete_mode=delete_mode,
                        )
                        success = result.get('errors', 0) == 0
                        manager.update_file_states(config_id, source_path, folder_id)
                    finally:
                        manager.disconnect()
                else:
                    raise ValueError('Не удалось авторизоваться в Google Drive')

            elif target_type == 'ftp':
                manager = self.sync_managers['ftp']
                server = target_settings.get('server')
                port = int(target_settings.get('port', 21))
                username = target_settings.get('username')
                password = self._decrypt(target_settings.get('password'))
                folder = target_settings.get('folder', '/')
                connection_mode = target_settings.get('connection_mode', 'passive')
                use_ssl = bool(target_settings.get('use_ssl', False))
                encoding = target_settings.get('encoding', 'UTF-8')

                if manager.connect(server, username, password, port, use_ssl, connection_mode, encoding):
                    try:
                        result = manager.sync_folders(
                            config_id,
                            source_path,
                            folder,
                            callback=lambda msg, *_: emit(msg),
                            direction=target_settings.get('direction', 'upload'),
                            delete_mode=delete_mode,
                        )
                        success = result.get('errors', 0) == 0
                        manager.update_file_states(config_id, source_path, folder)
                    finally:
                        manager.disconnect()
                else:
                    raise ValueError('Подключение к FTP не удалось')

            elif target_type == 'smb':
                manager = self.sync_managers['smb']
                server = target_settings.get('server')
                port = int(target_settings.get('port', 445))
                username = target_settings.get('username')
                password = self._decrypt(target_settings.get('password'))
                domain = target_settings.get('domain')
                guest = bool(target_settings.get('guest', False))
                share = target_settings.get('share')
                path = target_settings.get('path', '')
                large_files = bool(target_settings.get('large_files', True))

                if manager.connect(server, username, password, domain, port, guest):
                    try:
                        target_info = {
                            'share_name': share,
                            'path': path,
                            'large_files': large_files,
                        }
                        result = manager.sync_folders(
                            config_id,
                            source_path,
                            target_info,
                            callback=lambda msg, *_: emit(msg),
                            direction=target_settings.get('direction', 'upload'),
                            delete_mode=delete_mode,
                        )
                        success = result.get('errors', 0) == 0
                        manager.update_file_states(config_id, source_path, target_info)
                    finally:
                        manager.disconnect()
                else:
                    raise ValueError('Подключение к SMB не удалось')

            elif target_type == 's3':
                manager = self.sync_managers['s3']
                access_key = target_settings.get('access_key')
                secret_key = self._decrypt(target_settings.get('secret_key'))
                endpoint = target_settings.get('endpoint')
                region = target_settings.get('region', 'us-east-1')
                bucket = target_settings.get('bucket')
                prefix = target_settings.get('prefix', '')
                use_https = bool(target_settings.get('use_https', True))
                storage_class = target_settings.get('storage_class', 'STANDARD')
                sse = bool(target_settings.get('sse', False))

                if manager.connect(access_key, secret_key, endpoint, region, use_https):
                    target_info = {
                        'bucket_name': bucket,
                        'prefix': prefix,
                        'storage_class': storage_class,
                        'sse': sse,
                    }
                    result = manager.sync_folders(
                        config_id,
                        source_path,
                        target_info,
                        callback=lambda msg, *_: emit(msg),
                        direction=target_settings.get('direction', 'upload'),
                        delete_mode=delete_mode,
                    )
                    success = result.get('errors', 0) == 0
                    manager.update_file_states(config_id, source_path, target_info)
                else:
                    raise ValueError('Подключение к S3 не удалось')

            elif target_type == 'dropbox':
                manager = self.sync_managers['dropbox']
                token = self._decrypt(target_settings.get('token'))
                folder = target_settings.get('folder', '/')
                if manager.authenticate(token):
                    target_info = {
                        'folder': folder,
                        'ignore_dropbox_files': bool(target_settings.get('ignore_dropbox_files', True)),
                        'selective_sync': bool(target_settings.get('selective_sync', False)),
                    }
                    result = manager.sync_folders(
                        config_id,
                        source_path,
                        target_info,
                        callback=lambda msg, *_: emit(msg),
                        direction=target_settings.get('direction', 'upload'),
                        delete_mode=delete_mode,
                    )
                    success = result.get('errors', 0) == 0
                    manager.update_file_states(config_id, source_path, folder)
                else:
                    raise ValueError('Авторизация в Dropbox не удалась')

            else:
                raise ValueError(f"Тип цели '{target_type}' пока не поддерживается")

            status = 'completed' if success else 'failed'

            # Формируем детальное сообщение из результата
            if result:
                message = f"Синхронизация завершена. " \
                         f"Скопировано: {result.get('copied', 0)}, " \
                         f"Обновлено: {result.get('updated', 0)}, " \
                         f"Удалено: {result.get('deleted', 0)}, " \
                         f"Пропущено: {result.get('skipped', 0)}, " \
                         f"Ошибок: {result.get('errors', 0)}"
            else:
                message = 'Синхронизация завершена успешно' if success else 'Синхронизация завершилась ошибкой'

            # Обновляем запись в истории только если менеджер ещё не обновил её
            # (LocalSyncManager обновляет сам, но другие менеджеры могут не обновлять)
            history_record = self.db_manager.get_sync_history_record(history_id)
            if history_record and history_record.get('status') in ['running', 'in_progress']:
                self.db_manager.update_sync_history(
                    history_id,
                    status=status,
                    message=message,
                    end_time=datetime.utcnow(),
                    files_copied=result.get('copied', 0),
                    files_updated=result.get('updated', 0),
                    files_deleted=result.get('deleted', 0),
                    errors=result.get('errors', 0),
                )

            emit(message, level='info' if success else 'error')
            return success

        except Exception as exc:
            error_message = f"Ошибка синхронизации конфигурации {config_id}: {exc}"
            self.error_handler.log_error(error_message)
            self.db_manager.update_sync_history(
                history_id,
                status='failed',
                message=error_message,
                end_time=datetime.utcnow(),
            )
            emit(error_message, level='error')
            return False

    # ------------------------------------------------------------------
    # connection testing
    # ------------------------------------------------------------------
    def test_connection(self, target_type: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Test connection to storage backend."""
        try:
            if target_type == 'local':
                return self._test_local_connection(settings)
            elif target_type == 'gdrive':
                return self._test_gdrive_connection(settings)
            elif target_type == 'ftp':
                return self._test_ftp_connection(settings)
            elif target_type == 'smb':
                return self._test_smb_connection(settings)
            elif target_type == 's3':
                return self._test_s3_connection(settings)
            elif target_type == 'dropbox':
                return self._test_dropbox_connection(settings)
            else:
                return {'success': False, 'message': f'Неизвестный тип хранилища: {target_type}'}
        except Exception as exc:
            return {'success': False, 'message': f'Ошибка тестирования: {str(exc)}'}

    def _test_local_connection(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Test local folder access."""
        import os
        path = settings.get('path', '')
        if not path:
            return {'success': False, 'message': 'Не указан путь к папке'}
        if not os.path.exists(path):
            return {'success': False, 'message': f'Папка не существует: {path}'}
        if not os.path.isdir(path):
            return {'success': False, 'message': f'Указанный путь не является папкой: {path}'}
        if not os.access(path, os.W_OK):
            return {'success': False, 'message': f'Нет прав на запись в папку: {path}'}
        return {'success': True, 'message': 'Папка доступна для записи'}

    def _test_gdrive_connection(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Test Google Drive connection."""
        credentials_file = settings.get('credentials_file', '')
        if not credentials_file:
            return {'success': False, 'message': 'Не указан файл учетных данных'}

        manager = self.sync_managers['gdrive']
        if manager.authenticate(credentials_file):
            try:
                # Try to list root folder
                folder_id = manager.get_folder_id('/')
                return {'success': True, 'message': 'Успешное подключение к Google Drive'}
            except Exception as exc:
                return {'success': False, 'message': f'Ошибка доступа к Google Drive: {str(exc)}'}
            finally:
                manager.disconnect()
        else:
            return {'success': False, 'message': 'Не удалось авторизоваться в Google Drive'}

    def _test_ftp_connection(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Test FTP connection."""
        server = settings.get('server', '')
        port = int(settings.get('port', 21))
        username = settings.get('username', '')
        password = self._decrypt(settings.get('password', ''))
        use_ssl = bool(settings.get('use_ssl', False))

        if not server:
            return {'success': False, 'message': 'Не указан сервер'}

        manager = self.sync_managers['ftp']
        if manager.connect(server, username, password, port, use_ssl):
            try:
                return {'success': True, 'message': f'Успешное подключение к {server}:{port}'}
            finally:
                manager.disconnect()
        else:
            return {'success': False, 'message': f'Не удалось подключиться к {server}:{port}'}

    def _test_smb_connection(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Test SMB connection."""
        server = settings.get('server', '')
        port = int(settings.get('port', 445))
        username = settings.get('username', '')
        password = self._decrypt(settings.get('password', ''))
        domain = settings.get('domain', '')
        share = settings.get('share', '')

        if not server:
            return {'success': False, 'message': 'Не указан сервер'}
        if not share:
            return {'success': False, 'message': 'Не указана сетевая папка (share)'}

        manager = self.sync_managers['smb']
        if manager.connect(server, username, password, domain, port):
            try:
                return {'success': True, 'message': f'Успешное подключение к \\\\{server}\\{share}'}
            finally:
                manager.disconnect()
        else:
            return {'success': False, 'message': f'Не удалось подключиться к \\\\{server}\\{share}'}

    def _test_s3_connection(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Test S3 connection."""
        access_key = settings.get('access_key', '')
        secret_key = self._decrypt(settings.get('secret_key', ''))
        endpoint = settings.get('endpoint', '')
        region = settings.get('region', 'us-east-1')
        bucket = settings.get('bucket', '')

        if not access_key or not secret_key:
            return {'success': False, 'message': 'Не указаны ключи доступа'}
        if not bucket:
            return {'success': False, 'message': 'Не указан bucket'}

        manager = self.sync_managers['s3']
        if manager.connect(access_key, secret_key, endpoint, region):
            try:
                # Try to list bucket
                manager.s3_client.head_bucket(Bucket=bucket)
                return {'success': True, 'message': f'Успешное подключение к bucket "{bucket}"'}
            except Exception as exc:
                return {'success': False, 'message': f'Ошибка доступа к bucket: {str(exc)}'}
        else:
            return {'success': False, 'message': 'Не удалось подключиться к S3'}

    def _test_dropbox_connection(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Test Dropbox connection."""
        token = self._decrypt(settings.get('token', ''))

        if not token:
            return {'success': False, 'message': 'Не указан токен доступа'}

        manager = self.sync_managers['dropbox']
        if manager.authenticate(token):
            try:
                # Try to get account info
                account_info = manager.dbx.users_get_current_account()
                return {'success': True, 'message': f'Подключено к аккаунту: {account_info.name.display_name}'}
            except Exception as exc:
                return {'success': False, 'message': f'Ошибка доступа к Dropbox: {str(exc)}'}
        else:
            return {'success': False, 'message': 'Не удалось авторизоваться в Dropbox'}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _decrypt(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        try:
            decrypted = self.encryption_manager.decrypt(value)
            return decrypted or value
        except Exception:
            return value
