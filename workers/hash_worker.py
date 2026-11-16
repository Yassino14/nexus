"""
Background QThread Worker for Multistage SHA-256 Duplicate Detection.
"""

from __future__ import annotations

from typing import List

from config.settings import SettingsManager
from core.duplicate_engine import DuplicateEngine
from ui.qt_compat import QThread, Signal


class DuplicateHashWorker(QThread):
    """Executes multistage duplicate scan and SHA-256 hashing on a background thread."""

    progress = Signal(str, int, int)  # stage_name, current, total
    completed = Signal(object)        # DuplicateScanReport
    error = Signal(str)

    def __init__(
        self,
        roots: List[str],
        min_size_bytes: int,
        settings_mgr: SettingsManager,
        parent: object = None,
    ) -> None:
        super().__init__(parent)
        self.roots = roots
        self.min_size_bytes = min_size_bytes
        self.settings_mgr = settings_mgr
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            engine = DuplicateEngine(self.settings_mgr)
            report = engine.find_duplicates(
                self.roots,
                min_size_bytes=self.min_size_bytes,
                cancel_check=self.is_cancelled,
                progress_callback=lambda stg, cur, tot: self.progress.emit(stg, cur, tot),
            )
            self.completed.emit(report)
        except Exception as e:
            self.error.emit(str(e))
