"""
Background QThread Worker for Filesystem Scanning and Optional SQLite Indexing.
Supports real-time progress reporting and instant user cancellation.
"""

from __future__ import annotations

from typing import Optional

from config.settings import SettingsManager
from core.file_scanner import FileScanner, ScanSummary
from database.database import LocalDatabase
from database.index_manager import IndexManager
from ui.qt_compat import QThread, Signal


class ScanWorker(QThread):
    """Executes directory scan and/or SQLite indexing on a background thread."""

    progress = Signal(int, int, str)  # files_count, folders_count, current_path
    completed = Signal(object)        # ScanSummary or dict
    error = Signal(str)

    def __init__(
        self,
        root_path: str,
        settings_mgr: SettingsManager,
        db: Optional[LocalDatabase] = None,
        update_index: bool = False,
        incremental: bool = True,
        parent: object = None,
    ) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.settings_mgr = settings_mgr
        self.db = db
        self.update_index = update_index
        self.incremental = incremental
        self._cancelled = False

    def cancel(self) -> None:
        """Request immediate cooperative cancellation."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            if self.update_index and self.db and self.db.is_available:
                idx_mgr = IndexManager(self.db, self.settings_mgr)
                idx_mgr.index_directory(
                    self.root_path,
                    incremental=self.incremental,
                    cancel_check=self.is_cancelled,
                    progress_callback=lambda f, d, p: self.progress.emit(f, d, p),
                )

            scanner = FileScanner(self.settings_mgr)
            summary = scanner.scan_summary(
                self.root_path,
                cancel_check=self.is_cancelled,
                progress_callback=lambda s: self.progress.emit(
                    s.files_count, s.folders_count, s.root_path
                ),
            )
            self.completed.emit(summary)
        except Exception as e:
            self.error.emit(str(e))
