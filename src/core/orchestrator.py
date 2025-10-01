import logging
from typing import Dict

from src.core.database import DatabaseManager
from src.core.error_handler import ErrorHandler
from src.core.file_monitor import FileMonitor
from src.core.scheduler import SyncScheduler
from src.sync.service import SyncService

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    """Coordinates background services used by the NiceGUI application."""

    def __init__(self, db_manager: DatabaseManager, error_handler: ErrorHandler) -> None:
        self.db_manager = db_manager
        self.error_handler = error_handler
        self.sync_service = SyncService(db_manager, error_handler)
        self.file_monitor = FileMonitor(db_manager, error_handler, sync_callback=self.trigger_sync)
        self.scheduler = SyncScheduler(db_manager, self, error_handler)
        self.started = False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.started:
            return
        logger.info('Запуск оркестратора FileSync')
        if not self.file_monitor.start():
            logger.warning('Мониторинг файлов не был запущен (возможно watchdog не установлен)')
        if not self.scheduler.start():
            logger.warning('Планировщик синхронизации не был запущен')
        self.started = True
        self.reload_configuration()

    def stop(self) -> None:
        if not self.started:
            return
        logger.info('Остановка оркестратора FileSync')
        try:
            self.scheduler.stop()
        finally:
            self.file_monitor.stop()
            self.started = False

    # ------------------------------------------------------------------
    # scheduler API (used by SyncScheduler)
    # ------------------------------------------------------------------
    def sync_config(self, config_id: int) -> bool:
        """SyncScheduler callback."""
        return self.sync_service.sync_config(config_id)

    # ------------------------------------------------------------------
    # configuration & runtime reloading
    # ------------------------------------------------------------------
    def reload_configuration(self, initial_sync: bool = True) -> None:
        configs = self.db_manager.get_all_sync_configs()
        logger.info('Перезагрузка конфигурации (%s элементов)', len(configs))
        self._sync_file_monitors(configs)
        self._sync_schedules(configs)

        # Запускаем начальную синхронизацию для всех активных конфигураций
        if initial_sync and self.started:
            logger.info('Запуск начальной синхронизации для %d активных конфигураций', len([c for c in configs if c['is_active']]))
            for cfg in configs:
                if cfg['is_active']:
                    logger.info('Начальная синхронизация конфигурации %s: %s -> %s',
                              cfg['id'], cfg.get('source_path'), cfg.get('target_type'))
                    self.trigger_sync(cfg['id'])

    def _sync_file_monitors(self, configs) -> None:
        desired: Dict[str, int] = {}
        logger.info('Синхронизация мониторинга файлов, всего конфигураций: %d', len(configs))
        for cfg in configs:
            logger.debug('Config %s: realtime=%s, active=%s, source=%s',
                        cfg.get('id'), cfg.get('realtime_monitor'), cfg.get('is_active'), cfg.get('source_path'))
            if cfg['realtime_monitor'] and cfg['is_active']:
                source_path = cfg.get('source_path')
                if source_path:
                    desired[source_path] = cfg['id']
                    logger.info('Добавлен путь для мониторинга: %s (config=%s)', source_path, cfg['id'])

        logger.info('Всего путей для мониторинга: %d', len(desired))

        # remove outdated watches
        for path in list(self.file_monitor.observers.keys()):
            if path not in desired:
                logger.info('Удаление слежения за %s', path)
                self.file_monitor.remove_watch(path)

        # add new watches
        for path, config_id in desired.items():
            if path not in self.file_monitor.observers:
                logger.info('Попытка активировать мониторинг %s (config=%s)', path, config_id)
                if self.file_monitor.add_watch(path, config_id):
                    logger.info('✅ Мониторинг %s активирован (config=%s)', path, config_id)
                else:
                    logger.error('❌ Не удалось активировать мониторинг %s', path)
            else:
                logger.debug('Мониторинг %s уже активен', path)

    def _sync_schedules(self, configs) -> None:
        desired = {
            cfg['id']: cfg
            for cfg in configs
            if cfg['is_active'] and cfg.get('schedule_enabled') and cfg.get('schedule_type') and cfg.get('schedule_value')
        }

        with self.scheduler.lock:
            existing = set(self.scheduler.schedules.keys())

        for config_id in existing - desired.keys():
            logger.info('Удаление планировщика для конфигурации %s', config_id)
            self.scheduler.remove_schedule(config_id)

        for config_id, cfg in desired.items():
            if config_id in existing:
                continue
            added = self.scheduler.add_schedule(
                config_id,
                cfg['schedule_type'],
                cfg['schedule_value'],
            )
            if added:
                logger.info('Добавлен планировщик для конфигурации %s (%s)', config_id, cfg['schedule_type'])
            else:
                logger.error('Не удалось добавить планировщик для конфигурации %s', config_id)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def trigger_sync(self, config_id: int) -> bool:
        logger.info('Ручной запуск синхронизации для конфигурации %s', config_id)
        return self.sync_service.sync_config(config_id)

    def active_tasks(self):
        return self.scheduler.get_active_tasks()

    def monitored_paths(self):
        return list(self.file_monitor.observers.keys())
