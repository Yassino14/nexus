"""
Background QThread Worker for Deep Disk Analysis and Treemap Hierarchy Computation.
"""

from __future__ import annotations

from config.settings import SettingsManager
from core.disk_analyzer import DiskAnalyzer
from ui.qt_compat import QThread, Signal


class DiskAnalysisWorker(QThread):
    """Runs DiskAnalyzer on a background thread with progress updates and cancellation."""

    progress = Signal(int, str)  # scanned_items, current_dir
    completed = Signal(object)   # DiskAnalysisResult
    error = Signal(str)

    def __init__(
        self,
        root_path: str,
        large_threshold_bytes: int,
        settings_mgr: SettingsManager,
        parent: object = None,
    ) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.large_threshold_bytes = large_threshold_bytes
        self.settings_mgr = settings_mgr
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            analyzer = DiskAnalyzer(self.settings_mgr)
            res = analyzer.analyze(
                self.root_path,
                large_threshold_bytes=self.large_threshold_bytes,
                cancel_check=self.is_cancelled,
                progress_callback=lambda cnt, cur_dir: self.progress.emit(cnt, cur_dir),
            )
            self.completed.emit(res)
        except Exception as e:
            self.error.emit(str(e))
