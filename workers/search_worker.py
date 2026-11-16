"""
Background QThread Worker for Universal Search Engine (Indexed & Direct Modes).
"""

from __future__ import annotations

from typing import Optional

from config.settings import SettingsManager
from core.search_engine import SearchEngine, SearchQuery
from database.database import LocalDatabase
from ui.qt_compat import QThread, Signal


class SearchWorker(QThread):
    """Executes SearchQuery asynchronously without blocking the UI thread."""

    partial_results = Signal(list, int, str)  # matches_so_far, scanned_count, current_dir
    results_ready = Signal(list)              # List[ScannedEntry]
    error = Signal(str)

    def __init__(
        self,
        query: SearchQuery,
        db: Optional[LocalDatabase],
        settings_mgr: SettingsManager,
        parent: object = None,
    ) -> None:
        super().__init__(parent)
        self.query = query
        self.db = db
        self.settings_mgr = settings_mgr
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            engine = SearchEngine(self.db, self.settings_mgr)
            results = engine.search(
                self.query,
                cancel_check=self.is_cancelled,
                progress_callback=lambda res, cnt, cur: self.partial_results.emit(res, cnt, cur),
            )
            if not self._cancelled:
                self.results_ready.emit(results)
        except Exception as e:
            self.error.emit(str(e))
