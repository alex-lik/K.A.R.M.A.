import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional


class DatabaseManager:
    """SQLite-backed storage for FileSync configuration and runtime data."""

    def __init__(self, db_path: str = "sync_app.db") -> None:
        self.db_path = db_path
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # connection helpers
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # schema management
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    source_path TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_path TEXT DEFAULT '',
                    target_settings TEXT DEFAULT '{}',
                    sync_mode TEXT NOT NULL DEFAULT 'realtime',
                    sync_type TEXT NOT NULL DEFAULT 'one_way',
                    delete_missing INTEGER NOT NULL DEFAULT 1,
                    ignore_hidden INTEGER NOT NULL DEFAULT 1,
                    ignore_mask TEXT DEFAULT '',
                    preserve_permissions INTEGER NOT NULL DEFAULT 0,
                    preserve_timestamps INTEGER NOT NULL DEFAULT 1,
                    verify_integrity INTEGER NOT NULL DEFAULT 0,
                    realtime_monitor INTEGER NOT NULL DEFAULT 0,
                    auto_sync_on_change INTEGER NOT NULL DEFAULT 0,
                    filter_settings TEXT DEFAULT '{}',
                    schedule_enabled INTEGER NOT NULL DEFAULT 0,
                    schedule_type TEXT,
                    schedule_value TEXT,
                    run_on_startup INTEGER NOT NULL DEFAULT 0,
                    run_only_on_changes INTEGER NOT NULL DEFAULT 0,
                    limit_time INTEGER NOT NULL DEFAULT 0,
                    sync_options TEXT DEFAULT '{}',
                    schedule_config TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    files_count INTEGER DEFAULT 0,
                    files_processed INTEGER DEFAULT 0,
                    files_copied INTEGER DEFAULT 0,
                    files_updated INTEGER DEFAULT 0,
                    files_deleted INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    error_details TEXT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES sync_configs (id) ON DELETE CASCADE
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER DEFAULT 0,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES sync_configs (id) ON DELETE CASCADE
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS file_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    file_hash TEXT,
                    modified_time REAL,
                    sync_status TEXT DEFAULT 'pending',
                    last_sync TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES sync_configs (id) ON DELETE CASCADE,
                    UNIQUE(config_id, file_path)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_file_operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    history_id INTEGER NOT NULL,
                    operation_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    source_path TEXT,
                    target_path TEXT,
                    file_size INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'success',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (history_id) REFERENCES sync_history (id) ON DELETE CASCADE
                )
                """
            )

            self._ensure_schema(cursor)

    def _ensure_schema(self, cursor: sqlite3.Cursor) -> None:
        required_columns = [
            ("sync_configs", "description TEXT DEFAULT ''"),
            ("sync_configs", "target_path TEXT DEFAULT ''"),
            ("sync_configs", "target_settings TEXT DEFAULT '{}'"),
            ("sync_configs", "sync_mode TEXT NOT NULL DEFAULT 'realtime'"),
            ("sync_configs", "sync_type TEXT NOT NULL DEFAULT 'one_way'"),
            ("sync_configs", "delete_missing INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "ignore_hidden INTEGER NOT NULL DEFAULT 1"),
            ("sync_configs", "ignore_mask TEXT DEFAULT ''"),
            ("sync_configs", "preserve_permissions INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "preserve_timestamps INTEGER NOT NULL DEFAULT 1"),
            ("sync_configs", "verify_integrity INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "realtime_monitor INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "auto_sync_on_change INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "filter_settings TEXT DEFAULT '{}'"),
            ("sync_configs", "schedule_enabled INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "schedule_type TEXT"),
            ("sync_configs", "schedule_value TEXT"),
            ("sync_configs", "run_on_startup INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "run_only_on_changes INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "limit_time INTEGER NOT NULL DEFAULT 0"),
            ("sync_configs", "sync_options TEXT DEFAULT '{}'"),
            ("sync_configs", "schedule_config TEXT"),
            ("sync_configs", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("sync_history", "files_count INTEGER DEFAULT 0"),
            ("sync_history", "files_processed INTEGER DEFAULT 0"),
            ("sync_history", "files_copied INTEGER DEFAULT 0"),
            ("sync_history", "files_updated INTEGER DEFAULT 0"),
            ("sync_history", "files_deleted INTEGER DEFAULT 0"),
            ("sync_history", "errors INTEGER DEFAULT 0"),
            ("sync_history", "error_details TEXT"),
            ("sync_history", "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("sync_history", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("sync_history", "start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("sync_history", "end_time TIMESTAMP")
        ]

        for table, column_def in required_columns:
            self._ensure_column(cursor, table, column_def)

    def _ensure_column(self, cursor: sqlite3.Cursor, table: str, column_def: str) -> None:
        column_name = column_def.split()[0]
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

    # ------------------------------------------------------------------
    # helper utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _bool_to_int(value: Optional[bool]) -> int:
        return 1 if value else 0

    @staticmethod
    def _int_to_bool(value: Any) -> bool:
        return bool(int(value)) if value is not None else False

    @staticmethod
    def _load_json(value: Any, default: Any) -> Any:
        if value in (None, ""):
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    # ------------------------------------------------------------------
    # configuration CRUD
    # ------------------------------------------------------------------
    def add_sync_config(
        self,
        name: str,
        source_path: str,
        target_type: str,
        target_path: str = '',
        sync_mode: str = 'realtime',
        sync_type: str = 'one_way',
        sync_options: Optional[Dict[str, Any]] = None,
        schedule_config: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
        description: str = '',
        target_settings: Optional[Any] = None,
        delete_missing: bool = False,
        ignore_hidden: bool = True,
        ignore_mask: str = '',
        preserve_permissions: bool = False,
        preserve_timestamps: bool = True,
        verify_integrity: bool = False,
        realtime_monitor: bool = False,
        auto_sync_on_change: bool = False,
        filter_settings: Optional[Any] = None,
        schedule_enabled: bool = False,
        schedule_type: Optional[str] = None,
        schedule_value: Optional[str] = None,
        run_on_startup: bool = False,
        run_only_on_changes: bool = False,
        limit_time: int = 0,
    ) -> int:
        options_json = json.dumps(sync_options or {})
        schedule_json = json.dumps(schedule_config) if schedule_config else None
        filter_json = json.dumps(filter_settings) if isinstance(filter_settings, (dict, list)) else (filter_settings or json.dumps({}))
        target_settings_json = json.dumps(target_settings) if isinstance(target_settings, (dict, list)) else (target_settings or json.dumps({}))

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sync_configs (
                    name, description, source_path, target_type, target_path, target_settings,
                    sync_mode, sync_type, delete_missing, ignore_hidden, ignore_mask,
                    preserve_permissions, preserve_timestamps, verify_integrity,
                    realtime_monitor, auto_sync_on_change, filter_settings,
                    schedule_enabled, schedule_type, schedule_value,
                    run_on_startup, run_only_on_changes, limit_time,
                    sync_options, schedule_config, is_active,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    name,
                    description or '',
                    source_path,
                    target_type,
                    target_path or '',
                    target_settings_json,
                    sync_mode,
                    sync_type,
                    self._bool_to_int(delete_missing),
                    self._bool_to_int(ignore_hidden),
                    ignore_mask or '',
                    self._bool_to_int(preserve_permissions),
                    self._bool_to_int(preserve_timestamps),
                    self._bool_to_int(verify_integrity),
                    self._bool_to_int(realtime_monitor),
                    self._bool_to_int(auto_sync_on_change),
                    filter_json,
                    self._bool_to_int(schedule_enabled),
                    schedule_type,
                    schedule_value,
                    self._bool_to_int(run_on_startup),
                    self._bool_to_int(run_only_on_changes),
                    int(limit_time or 0),
                    options_json,
                    schedule_json,
                    self._bool_to_int(is_active),
                ),
            )
            return cursor.lastrowid

    def update_sync_config(
        self,
        config_id: int,
        **updates: Any,
    ) -> None:
        if not updates:
            return

        allowed = {
            'name', 'description', 'source_path', 'target_type', 'target_path', 'target_settings',
            'sync_mode', 'sync_type', 'delete_missing', 'ignore_hidden', 'ignore_mask',
            'preserve_permissions', 'preserve_timestamps', 'verify_integrity',
            'realtime_monitor', 'auto_sync_on_change', 'filter_settings',
            'schedule_enabled', 'schedule_type', 'schedule_value',
            'run_on_startup', 'run_only_on_changes', 'limit_time',
            'sync_options', 'schedule_config', 'is_active'
        }

        set_clauses: List[str] = []
        params: List[Any] = []

        for key, value in updates.items():
            if key not in allowed:
                continue

            if key in {'delete_missing', 'ignore_hidden', 'preserve_permissions', 'preserve_timestamps',
                       'verify_integrity', 'realtime_monitor', 'auto_sync_on_change',
                       'schedule_enabled', 'run_on_startup', 'run_only_on_changes', 'is_active'}:
                value = self._bool_to_int(value)
            elif key in {'filter_settings', 'target_settings', 'sync_options', 'schedule_config'}:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
            elif key == 'limit_time' and value is not None:
                value = int(value)

            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(config_id)

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE sync_configs SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )

    def update_sync_schedule(
        self,
        config_id: int,
        schedule_type: Optional[str],
        schedule_value: Optional[str],
        enabled: bool,
        run_on_startup: bool = False,
        run_only_on_changes: bool = False,
        limit_time: int = 0,
    ) -> None:
        self.update_sync_config(
            config_id,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            schedule_enabled=enabled,
            run_on_startup=run_on_startup,
            run_only_on_changes=run_only_on_changes,
            limit_time=limit_time,
        )

    def delete_sync_config(self, config_id: int) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sync_configs WHERE id = ?", (config_id,))

    def get_sync_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_configs WHERE id = ?", (config_id,))
            row = cursor.fetchone()
        return self._normalise_config(dict(row)) if row else None

    def get_sync_configs(self, active_only: bool = True) -> List[Dict[str, Any]]:
        query = "SELECT * FROM sync_configs"
        params: List[Any] = []
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name"
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [self._normalise_config(dict(row)) for row in rows]

    def get_all_sync_configs(self) -> List[Dict[str, Any]]:
        return self.get_sync_configs(active_only=False)

    def get_all_config_ids(self) -> List[int]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sync_configs ORDER BY id")
            return [row[0] for row in cursor.fetchall()]

    def _normalise_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        config['delete_missing'] = self._int_to_bool(config.get('delete_missing'))
        config['ignore_hidden'] = self._int_to_bool(config.get('ignore_hidden'))
        config['preserve_permissions'] = self._int_to_bool(config.get('preserve_permissions'))
        config['preserve_timestamps'] = self._int_to_bool(config.get('preserve_timestamps'))
        config['verify_integrity'] = self._int_to_bool(config.get('verify_integrity'))
        config['realtime_monitor'] = self._int_to_bool(config.get('realtime_monitor'))
        config['auto_sync_on_change'] = self._int_to_bool(config.get('auto_sync_on_change'))
        config['schedule_enabled'] = self._int_to_bool(config.get('schedule_enabled'))
        config['run_on_startup'] = self._int_to_bool(config.get('run_on_startup'))
        config['run_only_on_changes'] = self._int_to_bool(config.get('run_only_on_changes'))
        config['is_active'] = self._int_to_bool(config.get('is_active'))
        config['limit_time'] = int(config.get('limit_time') or 0)
        config['sync_options'] = self._load_json(config.get('sync_options'), {})
        config['schedule_config'] = self._load_json(config.get('schedule_config'), {})
        config['filter_settings'] = self._load_json(config.get('filter_settings'), {})
        config['target_settings'] = self._load_json(config.get('target_settings'), {})
        config['description'] = config.get('description') or ''
        config['target_path'] = config.get('target_path') or ''
        return config

    # ------------------------------------------------------------------
    # history management
    # ------------------------------------------------------------------
    def add_sync_history(
        self,
        config_id: int,
        status: str,
        message: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        files_count: int = 0,
        files_processed: int = 0,
        files_copied: int = 0,
        files_updated: int = 0,
        files_deleted: int = 0,
        errors: int = 0,
        error_details: Optional[str] = None,
    ) -> int:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sync_history (
                    config_id, status, message, files_count, files_processed,
                    files_copied, files_updated, files_deleted, errors, error_details,
                    start_time, end_time, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    config_id,
                    status,
                    message,
                    files_count,
                    files_processed,
                    files_copied,
                    files_updated,
                    files_deleted,
                    errors,
                    error_details,
                    (start_time or datetime.utcnow()).isoformat(),
                    end_time.isoformat() if end_time else None,
                ),
            )
            return cursor.lastrowid

    def update_sync_history(self, history_id: int, **updates: Any) -> None:
        if not updates:
            return
        set_clauses: List[str] = []
        params: List[Any] = []
        for key, value in updates.items():
            if key not in {
                'status', 'message', 'files_count', 'files_processed', 'files_copied',
                'files_updated', 'files_deleted', 'errors', 'error_details',
                'start_time', 'end_time'
            }:
                continue
            if isinstance(value, datetime):
                value = value.isoformat()
            set_clauses.append(f"{key} = ?")
            params.append(value)
        if not set_clauses:
            return
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(history_id)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE sync_history SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )

    def get_sync_history(
        self,
        *args: Any,
        history_id: Optional[int] = None,
        config_id: Optional[int] = None,
        days: int = 0,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Any:
        if args:
            if len(args) == 1:
                history_id = args[0]
            elif len(args) == 2:
                config_id, days = args
            elif len(args) >= 3:
                config_id, days, status = args[:3]

        if history_id is not None and config_id is None:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM sync_history WHERE id = ?", (history_id,))
                row = cursor.fetchone()
            return dict(row) if row else None

        where_clauses = []
        params: List[Any] = []
        if config_id is not None:
            where_clauses.append("config_id = ?")
            params.append(config_id)
        if days and days > 0:
            threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
            where_clauses.append("start_time >= ?")
            params.append(threshold)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        where_sql = ' WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''
        query = f"SELECT * FROM sync_history{where_sql} ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_recent_sync_history(self, days: int = 0, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        return self.get_sync_history(history_id=None, config_id=None, days=days, status=status, limit=limit)

    def get_general_sync_stats(self, days: int = 0) -> List[Dict[str, Any]]:
        records = self.get_sync_history(history_id=None, config_id=None, days=days, limit=1000)
        total = len(records)
        completed = sum(1 for r in records if r.get('status') == 'completed')
        failed = sum(1 for r in records if r.get('status') in {'failed', 'error'})
        running = sum(1 for r in records if r.get('status') == 'running')
        files_processed = sum(int(r.get('files_processed') or 0) for r in records)
        files_deleted = sum(int(r.get('files_deleted') or 0) for r in records)
        total_errors = sum(int(r.get('errors') or 0) for r in records)
        durations: List[float] = []
        for r in records:
            start_time = r.get('start_time')
            end_time = r.get('end_time')
            if start_time and end_time:
                try:
                    start_dt = datetime.fromisoformat(start_time)
                    end_dt = datetime.fromisoformat(end_time)
                    durations.append(max(0.0, (end_dt - start_dt).total_seconds()))
                except ValueError:
                    continue
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        return [
            {'name': 'Всего синхронизаций', 'value': total, 'type': 'count'},
            {'name': 'Успешные', 'value': completed, 'type': 'count'},
            {'name': 'Неудачные', 'value': failed, 'type': 'count'},
            {'name': 'Активные', 'value': running, 'type': 'count'},
            {'name': 'Обработано файлов', 'value': files_processed, 'type': 'count'},
            {'name': 'Удалено файлов', 'value': files_deleted, 'type': 'count'},
            {'name': 'Ошибок за период', 'value': total_errors, 'type': 'count'},
            {'name': 'Средняя длительность (сек)', 'value': avg_duration, 'type': 'time'},
        ]

    def get_storage_sync_stats(self, days: int = 0) -> List[Dict[str, Any]]:
        where_clauses = []
        params: List[Any] = []
        if days and days > 0:
            threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
            where_clauses.append("sh.start_time >= ?")
            params.append(threshold)
        where_sql = 'WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''
        query = f"""
            SELECT sc.target_type,
                   COUNT(sh.id) AS total,
                   SUM(CASE WHEN sh.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN sh.status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed
            FROM sync_history sh
            JOIN sync_configs sc ON sc.id = sh.config_id
            {where_sql}
            GROUP BY sc.target_type
            ORDER BY sc.target_type
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [
            {
                'target_type': row['target_type'],
                'total': row['total'],
                'completed': row['completed'],
                'failed': row['failed'],
            }
            for row in rows
        ]

    def get_sync_history_record(self, history_id: int) -> Optional[Dict[str, Any]]:
        return self.get_sync_history(history_id=history_id)

    def get_synced_files(self, history_id: int) -> List[Dict[str, Any]]:
        # Placeholder for compatibility; detailed per-file history is not tracked yet.
        return []

    def get_sync_error_files(self, history_id: int) -> List[Dict[str, Any]]:
        # Placeholder for compatibility.
        return []

    def add_file_operation(
        self,
        history_id: int,
        operation_type: str,
        file_path: str,
        source_path: Optional[str] = None,
        target_path: Optional[str] = None,
        file_size: int = 0,
        status: str = 'success',
        error_message: Optional[str] = None,
    ) -> int:
        """Добавить запись об операции с файлом"""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sync_file_operations (
                    history_id, operation_type, file_path, source_path, target_path,
                    file_size, status, error_message, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (history_id, operation_type, file_path, source_path, target_path, file_size, status, error_message),
            )
            return cursor.lastrowid

    def get_file_operations(self, history_id: int) -> List[Dict[str, Any]]:
        """Получить все операции с файлами для записи в истории"""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sync_file_operations
                WHERE history_id = ?
                ORDER BY created_at DESC
                """,
                (history_id,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_file_operations_summary(self, history_id: int) -> Dict[str, Any]:
        """Получить сводку по операциям с файлами"""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    operation_type,
                    COUNT(*) as count,
                    SUM(file_size) as total_size
                FROM sync_file_operations
                WHERE history_id = ?
                GROUP BY operation_type
                """,
                (history_id,),
            )
            rows = cursor.fetchall()

        summary = {
            'copied': {'count': 0, 'size': 0},
            'updated': {'count': 0, 'size': 0},
            'deleted': {'count': 0, 'size': 0},
        }

        for row in rows:
            op_type = row['operation_type']
            if op_type in summary:
                summary[op_type] = {
                    'count': row['count'],
                    'size': row['total_size'] or 0,
                }

        return summary

    def clear_sync_history(self, config_id: int) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sync_history WHERE config_id = ?", (config_id,))

    def cleanup_old_history(self, days: int = 30) -> int:
        threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM sync_history WHERE start_time < ?",
                (threshold,),
            )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # file state tracking
    # ------------------------------------------------------------------
    def update_file_state(
        self,
        config_id: int,
        file_path: str,
        file_hash: Optional[str] = None,
        modified_time: Optional[float] = None,
        sync_status: Optional[str] = None,
    ) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO file_states (
                    config_id, file_path, file_hash, modified_time, sync_status, last_sync
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (config_id, file_path, file_hash, modified_time, sync_status),
            )

    def get_file_states(self, config_id: int) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_states WHERE config_id = ?", (config_id,))
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def delete_file_state(self, config_id: int, file_path: str) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM file_states WHERE config_id = ? AND file_path = ?",
                (config_id, file_path),
            )

    # ------------------------------------------------------------------
    # task management
    # ------------------------------------------------------------------
    def add_sync_task(
        self,
        config_id: int,
        status: str,
        progress: int = 0,
        message: Optional[str] = None,
    ) -> int:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sync_tasks (config_id, status, progress, message, created_at, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (config_id, status, progress, message),
            )
            return cursor.lastrowid

    def update_sync_task(
        self,
        task_id: int,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        updates = []
        params: List[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if message is not None:
            updates.append("message = ?")
            params.append(message)
        if not updates:
            return
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE sync_tasks SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    def get_sync_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_sync_tasks(self, config_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            if config_id is None:
                cursor.execute("SELECT * FROM sync_tasks ORDER BY created_at DESC")
            else:
                cursor.execute(
                    "SELECT * FROM sync_tasks WHERE config_id = ? ORDER BY created_at DESC",
                    (config_id,),
                )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_active_sync_tasks(self) -> List[Dict[str, Any]]:
        completed_states = {'completed', 'cancelled', 'failed', 'error'}
        tasks = self.get_sync_tasks()
        return [task for task in tasks if task['status'] not in completed_states]

    def delete_sync_task(self, task_id: int) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sync_tasks WHERE id = ?", (task_id,))
