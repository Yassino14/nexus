"""
High-level SQLite index manager supporting initial indexing, incremental indexing,
interrupted scan recovery, stale entry pruning, and index statistics.
"""

from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config.settings import SettingsManager, classify_extension
from database.database import LocalDatabase


class IndexManager:
    """Manages filesystem indexing into the optional SQLite database."""

    def __init__(self, db: LocalDatabase, settings_mgr: SettingsManager) -> None:
        self.db = db
        self.settings_mgr = settings_mgr

    def get_index_stats(self, drive_prefix: Optional[str] = None) -> Dict[str, Any]:
        """Return summary statistics from the SQLite index."""
        if not self.db.is_available:
            return {
                "available": False,
                "files_count": 0,
                "folders_count": 0,
                "total_size": 0,
                "last_scan_time": None,
                "interrupted_sessions": 0,
            }

        where_clause = ""
        params: tuple = ()
        if drive_prefix:
            where_clause = "WHERE drive = ? OR path LIKE ?"
            params = (drive_prefix, f"{drive_prefix}%")

        rows = self.db.query(
            f"""
            SELECT
                SUM(CASE WHEN is_dir = 0 THEN 1 ELSE 0 END) AS files_count,
                SUM(CASE WHEN is_dir = 1 THEN 1 ELSE 0 END) AS folders_count,
                SUM(CASE WHEN is_dir = 0 THEN size ELSE 0 END) AS total_size,
                MAX(indexed_at) AS last_indexed
            FROM files
            {where_clause}
            """,
            params,
        )
        stat_row = rows[0] if rows else {}
        interrupted = self.db.query(
            "SELECT COUNT(*) AS cnt FROM scan_sessions WHERE status = 'interrupted'"
        )
        return {
            "available": True,
            "files_count": int(stat_row.get("files_count") or 0),
            "folders_count": int(stat_row.get("folders_count") or 0),
            "total_size": int(stat_row.get("total_size") or 0),
            "last_scan_time": stat_row.get("last_indexed"),
            "interrupted_sessions": int(interrupted[0]["cnt"]) if interrupted else 0,
        }

    def get_interrupted_sessions(self) -> List[Dict[str, Any]]:
        """Return any scan sessions that were interrupted prematurely."""
        return self.db.query(
            "SELECT * FROM scan_sessions WHERE status = 'interrupted' ORDER BY updated_at DESC"
        )

    def index_directory(
        self,
        root_path: str | Path,
        incremental: bool = True,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Index or incrementally update `root_path` in chunks without loading
        the entire filesystem into RAM.
        """
        root_str = os.path.abspath(str(root_path))
        if not self.db.is_available:
            return {
                "status": "disabled",
                "files_indexed": 0,
                "folders_indexed": 0,
                "total_bytes": 0,
            }

        now = time.time()
        self.db.execute(
            "INSERT INTO scan_sessions (root_path, status, started_at, updated_at) VALUES (?, 'running', ?, ?)",
            (root_str, now, now),
        )
        session_rows = self.db.query("SELECT MAX(id) AS sid FROM scan_sessions")
        session_id = session_rows[0]["sid"] if session_rows else None

        root_prefix = root_str if root_str.endswith(os.sep) else root_str + os.sep
        existing_mtimes: Dict[str, float] = {}
        if incremental:
            for r in self.db.query(
                "SELECT path, mtime FROM files WHERE path = ? OR substr(path, 1, ?) = ?",
                (root_str, len(root_prefix), root_prefix),
            ):
                existing_mtimes[r["path"]] = float(r["mtime"])

        batch: List[Dict[str, Any]] = []
        files_indexed = 0
        folders_indexed = 0
        total_bytes = 0
        seen_paths: set[str] = set()
        max_files = self.settings_mgr.settings.indexing_max_files
        content_enabled = self.settings_mgr.settings.content_indexing_enabled
        max_snippet_bytes = self.settings_mgr.settings.max_content_index_size_kb * 1024

        drive_id = os.path.splitdrive(root_str)[0]
        if drive_id and not drive_id.endswith(os.sep):
            drive_id += os.sep
        elif not drive_id:
            drive_id = "/"

        queue: deque[str] = deque([root_str])
        while queue:
            if cancel_check and cancel_check():
                if batch:
                    self.db.execute_Batch_upsert(batch)
                if session_id:
                    self.db.execute(
                        "UPDATE scan_sessions SET status='cancelled', updated_at=?, files_indexed=?, folders_indexed=?, total_bytes=? WHERE id=?",
                        (time.time(), files_indexed, folders_indexed, total_bytes, session_id),
                    )
                return {
                    "status": "cancelled",
                    "files_indexed": files_indexed,
                    "folders_indexed": folders_indexed,
                    "total_bytes": total_bytes,
                }

            current_dir = queue.popleft()
            if self.settings_mgr.is_path_excluded(current_dir):
                continue

            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        if cancel_check and cancel_check():
                            break
                        full_path = entry.path
                        if self.settings_mgr.is_path_excluded(full_path):
                            continue
                        try:
                            is_symlink = entry.is_symlink() or (
                                hasattr(entry, "is_junction") and entry.is_junction()
                            )
                            if is_symlink and not self.settings_mgr.settings.follow_symlinks:
                                continue
                            is_dir = entry.is_dir(follow_symlinks=False)
                            stat = entry.stat(follow_symlinks=False)
                        except OSError:
                            continue

                        seen_paths.add(full_path)
                        is_hidden = 1 if entry.name.startswith(".") or self._is_win_hidden(stat) else 0
                        if not self.settings_mgr.settings.show_hidden_files and is_hidden:
                            continue

                        if is_dir:
                            folders_indexed += 1
                            queue.append(full_path)
                            ext = ""
                            cat = "Folder"
                            size = 0
                        else:
                            files_indexed += 1
                            size = int(stat.st_size)
                            total_bytes += size
                            ext = os.path.splitext(entry.name)[1].lower()
                            cat = classify_extension(ext)

                        if incremental and full_path in existing_mtimes:
                            if abs(existing_mtimes[full_path] - stat.st_mtime) < 0.001:
                                continue

                        snippet = None
                        if (
                            content_enabled
                            and not is_dir
                            and size <= max_snippet_bytes
                            and ext in (".txt", ".md", ".py", ".json", ".csv", ".log", ".ini", ".xml", ".html", ".js", ".cs", ".java")
                        ):
                            snippet = self._read_text_snippet(full_path)

                        batch.append(
                            {
                                "path": full_path,
                                "parent_dir": current_dir,
                                "drive": drive_id,
                                "name": entry.name,
                                "name_lower": entry.name.lower(),
                                "extension": ext,
                                "category": cat,
                                "size": size,
                                "mtime": float(stat.st_mtime),
                                "ctime": float(getattr(stat, "st_ctime", stat.st_mtime)),
                                "atime": float(getattr(stat, "st_atime", stat.st_mtime)),
                                "is_dir": 1 if is_dir else 0,
                                "is_hidden": is_hidden,
                                "sha256": None,
                                "content_snippet": snippet,
                                "indexed_at": time.time(),
                            }
                        )

                        if len(batch) >= 500:
                            self.db.execute_Batch_upsert(batch)
                            batch.clear()
                            if session_id:
                                self.db.execute(
                                    "UPDATE scan_sessions SET updated_at=?, files_indexed=?, folders_indexed=?, total_bytes=?, last_directory=? WHERE id=?",
                                    (time.time(), files_indexed, folders_indexed, total_bytes, current_dir, session_id),
                                )
                            if progress_callback:
                                progress_callback(files_indexed, folders_indexed, current_dir)

                        if files_indexed >= max_files:
                            queue.clear()
                            break
            except OSError:
                continue

        if batch:
            self.db.execute_Batch_upsert(batch)
            batch.clear()

        # Prune deleted files during incremental scan if we completed cleanly
        if incremental and seen_paths and existing_mtimes:
            stale_paths = [
                p for p in existing_mtimes
                if p not in seen_paths and (p == root_str or p.startswith(root_prefix))
            ]
            for i in range(0, len(stale_paths), 200):
                chunk = stale_paths[i : i + 200]
                placeholders = ",".join("?" for _ in chunk)
                self.db.execute(f"DELETE FROM files WHERE path IN ({placeholders})", tuple(chunk))
                if self.db.fts5_available:
                    self.db.execute(f"DELETE FROM files_fts WHERE path IN ({placeholders})", tuple(chunk))

        if session_id:
            self.db.execute(
                "UPDATE scan_sessions SET status='completed', updated_at=?, completed_at=?, files_indexed=?, folders_indexed=?, total_bytes=? WHERE id=?",
                (time.time(), time.time(), files_indexed, folders_indexed, total_bytes, session_id),
            )
        if progress_callback:
            progress_callback(files_indexed, folders_indexed, root_str)

        return {
            "status": "completed",
            "files_indexed": files_indexed,
            "folders_indexed": folders_indexed,
            "total_bytes": total_bytes,
        }

    @staticmethod
    def _is_win_hidden(stat_res: os.stat_result) -> bool:
        attrs = getattr(stat_res, "st_file_attributes", 0)
        return bool(attrs & 0x2)  # FILE_ATTRIBUTE_HIDDEN

    @staticmethod
    def _read_text_snippet(file_path: str, max_chars: int = 4096) -> Optional[str]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(max_chars)
        except Exception:
            return None
