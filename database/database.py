"""
Resilient SQLite wrapper for NEXUS FILES.
Handles connection pooling per thread, integrity verification, corruption recovery,
and optional FTS5 search acceleration.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from database.schema import CREATE_FTS5_SQL, CREATE_TABLES_SQL, SCHEMA_VERSION


class LocalDatabase:
    """
    Lightweight optional SQLite backend.
    Never raises unhandled exceptions to callers if database is disabled,
    locked, or corrupted—automatically recovers or degrades gracefully.
    """

    def __init__(self, db_path: str | Path, enabled: bool = True) -> None:
        self.db_path = Path(db_path)
        self.enabled = enabled
        self.fts5_available = False
        self._lock = threading.RLock()
        self._healthy = False
        if self.enabled:
            self.initialize()

    @property
    def is_available(self) -> bool:
        return bool(self.enabled and self._healthy)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _session(self, commit: bool = False) -> Iterator[sqlite3.Connection]:
        """Open a SQLite connection and guarantee it is closed on exit."""
        conn = self._connect()
        try:
            yield conn
            if commit:
                conn.commit()
        except Exception:
            if commit:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            conn.close()

    def initialize(self) -> bool:
        """Create tables, check integrity, and enable FTS5 if supported."""
        if not self.enabled:
            self._healthy = False
            return False

        with self._lock:
            try:
                if self.db_path.exists():
                    if not self.check_integrity():
                        self._recover_corrupted_db()
                with self._session(commit=True) as conn:
                    conn.executescript(CREATE_TABLES_SQL)
                    conn.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                        ("schema_version", str(SCHEMA_VERSION)),
                    )
                    try:
                        conn.executescript(CREATE_FTS5_SQL)
                        self.fts5_available = True
                    except sqlite3.OperationalError:
                        self.fts5_available = False
                    # Mark any stale 'running' sessions from previous crash as 'interrupted'
                    conn.execute(
                        "UPDATE scan_sessions SET status = 'interrupted', updated_at = ? "
                        "WHERE status = 'running'",
                        (time.time(),),
                    )
                self._healthy = True
                return True
            except Exception:
                self._healthy = False
                return False

    def check_integrity(self) -> bool:
        """Verify SQLite magic header and run PRAGMA integrity_check."""
        if not self.db_path.exists():
            return True
        try:
            with open(self.db_path, "rb") as f:
                header = f.read(16)
            if len(header) > 0 and not header.startswith(b"SQLite format 3\x00"):
                return False
            with self._session() as conn:
                row = conn.execute("PRAGMA integrity_check;").fetchone()
                return bool(row and row[0] == "ok")
        except Exception:
            return False

    def _recover_corrupted_db(self) -> bool:
        """Backup corrupted database file and recreate a clean one."""
        try:
            backup_path = self.db_path.with_suffix(f".corrupt.{int(time.time())}.bak")
            if self.db_path.exists():
                shutil.move(str(self.db_path), str(backup_path))
            for wal_ext in ("-wal", "-shm"):
                aux = Path(str(self.db_path) + wal_ext)
                if aux.exists():
                    aux.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def rebuild(self) -> bool:
        """Drop and recreate the index cleanly."""
        with self._lock:
            try:
                if self.db_path.exists():
                    self.db_path.unlink(missing_ok=True)
                for wal_ext in ("-wal", "-shm"):
                    aux = Path(str(self.db_path) + wal_ext)
                    if aux.exists():
                        aux.unlink(missing_ok=True)
                return self.initialize()
            except Exception:
                return False

    def clear_all(self) -> bool:
        """Remove all indexed records while preserving schema."""
        if not self.is_available:
            return False
        with self._lock:
            try:
                with self._session(commit=True) as conn:
                    conn.execute("DELETE FROM files;")
                    conn.execute("DELETE FROM scan_sessions;")
                    if self.fts5_available:
                        conn.execute("DELETE FROM files_fts;")
                return True
            except Exception:
                return False

    def execute_Batch_upsert(self, records: List[Dict[str, Any]]) -> int:
        """
        Insert or update a batch of file metadata records with duplicate prevention.
        Synchronizes with FTS5 index when available.
        """
        if not self.is_available or not records:
            return 0
        with self._lock:
            try:
                with self._session(commit=True) as conn:
                    conn.executemany(
                        """
                        INSERT INTO files (
                            path, parent_dir, drive, name, name_lower, extension,
                            category, size, mtime, ctime, atime, is_dir, is_hidden,
                            sha256, content_snippet, indexed_at
                        ) VALUES (
                            :path, :parent_dir, :drive, :name, :name_lower, :extension,
                            :category, :size, :mtime, :ctime, :atime, :is_dir, :is_hidden,
                            :sha256, :content_snippet, :indexed_at
                        )
                        ON CONFLICT(path) DO UPDATE SET
                            parent_dir=excluded.parent_dir,
                            name=excluded.name,
                            name_lower=excluded.name_lower,
                            extension=excluded.extension,
                            category=excluded.category,
                            size=excluded.size,
                            mtime=excluded.mtime,
                            ctime=excluded.ctime,
                            atime=excluded.atime,
                            is_dir=excluded.is_dir,
                            is_hidden=excluded.is_hidden,
                            sha256=COALESCE(excluded.sha256, files.sha256),
                            content_snippet=COALESCE(excluded.content_snippet, files.content_snippet),
                            indexed_at=excluded.indexed_at
                        """,
                        records,
                    )
                    if self.fts5_available:
                        paths = [(r["path"],) for r in records]
                        conn.executemany("DELETE FROM files_fts WHERE path = ?", paths)
                        conn.executemany(
                            """
                            INSERT INTO files_fts (path, name, extension, parent_dir, content_snippet)
                            VALUES (:path, :name, :extension, :parent_dir, COALESCE(:content_snippet, ''))
                            """,
                            records,
                        )
                return len(records)
            except sqlite3.DatabaseError:
                self._recover_corrupted_db()
                self.initialize()
                return 0
            except Exception:
                return 0

    def query(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Execute a read query safely and return list of dicts."""
        if not self.is_available:
            return []
        try:
            with self._session() as conn:
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> bool:
        """Execute a single write statement safely."""
        if not self.is_available:
            return False
        with self._lock:
            try:
                with self._session(commit=True) as conn:
                    conn.execute(sql, params)
                return True
            except Exception:
                return False
