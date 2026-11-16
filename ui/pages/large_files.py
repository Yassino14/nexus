"""
Large File Finder Page — Predefined size filters (>100 MB, >500 MB, >1 GB, >5 GB)
and custom threshold discovery sorted largest first.
"""

from __future__ import annotations

from typing import List, Optional

from config.settings import SettingsManager
from core.file_operations import FileOperationsManager
from core.file_scanner import ScannedEntry
from core.search_engine import SearchEngine, SearchQuery
from database.database import LocalDatabase
from resources.icons.icon_provider import format_bytes
from ui.components.file_table import VirtualFileTableModel
from ui.qt_compat import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
    Signal,
)
from workers.search_worker import SearchWorker


class LargeFilesPage(QWidget):
    """Dedicated module for discovering and managing high-capacity files."""

    inspect_file_requested = Signal(str)

    def __init__(
        self,
        db: LocalDatabase,
        ops: FileOperationsManager,
        settings_mgr: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.ops = ops
        self.settings_mgr = settings_mgr
        self.engine = SearchEngine(db, settings_mgr)
        self.worker: Optional[SearchWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Large File Finder")
        title.setObjectName("PageTitle")
        sub = QLabel("Quickly isolate oversized archives, virtual machines, videos, and forgotten installers.")
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        # Predefined Threshold Buttons Row
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Quick Thresholds:"))
        for label, mb in [("> 100 MB", 100), ("> 500 MB", 500), ("> 1 GB", 1024), ("> 5 GB", 5120)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, val=mb: self.apply_preset_mb(val, synchronous=False))
            preset_row.addWidget(btn)

        self.custom_mb_spin = QSpinBox()
        self.custom_mb_spin.setRange(0, 100000)
        self.custom_mb_spin.setValue(100)
        self.custom_mb_spin.setSuffix(" MB")

        self.root_input = QLineEdit(self.settings_mgr.settings.default_drive)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_root)

        self.ext_input = QLineEdit()
        self.ext_input.setPlaceholderText("Extension filter (optional)")
        self.ext_input.setMaximumWidth(160)

        self.scan_btn = QPushButton("Find Large Files")
        self.scan_btn.setObjectName("PrimaryButton")
        self.scan_btn.clicked.connect(lambda: self.scan_large_files(synchronous=False))

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_scan)

        preset_row.addWidget(QLabel("Custom:"))
        preset_row.addWidget(self.custom_mb_spin)
        preset_row.addWidget(self.root_input, 1)
        preset_row.addWidget(self.browse_btn)
        preset_row.addWidget(self.ext_input)
        preset_row.addWidget(self.scan_btn)
        preset_row.addWidget(self.cancel_btn)
        layout.addLayout(preset_row)

        self.model = VirtualFileTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        self.summary_lbl = QLabel("Select a size threshold and click Find Large Files.")
        self.summary_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.summary_lbl)

    def _on_double_click(self, index: object) -> None:
        row = getattr(index, "row", lambda: -1)()
        entry = self.model.get_entry(row)
        if entry:
            self.inspect_file_requested.emit(entry.path)

    def _browse_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Folder to Scan for Large Files")
        if chosen:
            self.root_input.setText(chosen)

    def apply_preset_mb(self, mb_val: int, synchronous: bool = True) -> List[ScannedEntry]:
        self.custom_mb_spin.setValue(mb_val)
        return self.scan_large_files(synchronous=synchronous)

    def scan_large_files(
        self,
        min_bytes_override: Optional[int] = None,
        synchronous: bool = True,
    ) -> List[ScannedEntry]:
        min_b = (
            min_bytes_override
            if min_bytes_override is not None
            else self.custom_mb_spin.value() * 1024 * 1024
        )
        exts = [e.strip() for e in self.ext_input.text().split(",") if e.strip()]
        root_txt = self.root_input.text().strip() or "."
        roots = [] if root_txt == "ALL" else [root_txt]
        query = SearchQuery(
            roots=roots,
            extensions=exts,
            min_size_bytes=min_b,
            sort_by="size",
            sort_desc=True,
            search_mode="Direct",
        )
        if synchronous:
            results = self.engine.search(query)
            self._apply_results(results, min_b)
            return results

        if self.worker is not None:
            try:
                self.worker.results_ready.disconnect()
                self.worker.partial_results.disconnect()
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.cancel()

        self.scan_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.model.set_entries([])
        self.summary_lbl.setText(f"Scanning for files ≥ {format_bytes(min_b)}...")

        self.worker = SearchWorker(query, self.db, self.settings_mgr, self)
        self.worker.partial_results.connect(
            lambda partial, cnt, cur: (
                self.model.set_entries(sorted(partial, key=lambda x: x.size, reverse=True)),
                self.summary_lbl.setText(
                    f"Found {len(partial):,} large files so far (scanned {cnt:,} items — {cur[:55]})"
                ),
            )
        )
        self.worker.results_ready.connect(lambda res: self._apply_results(res, min_b))
        self.worker.start()
        return []

    def cancel_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.scan_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)
            self.summary_lbl.setText("Large file scan stopped.")

    def _apply_results(self, results: List[ScannedEntry], min_b: int) -> None:
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.model.set_entries(results)
        total_occupied = sum(e.size for e in results)
        self.summary_lbl.setText(
            f"Found {len(results):,} files ≥ {format_bytes(min_b)} • "
            f"Total Storage Occupied: {format_bytes(total_occupied)}"
        )
