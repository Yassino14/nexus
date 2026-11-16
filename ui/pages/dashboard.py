"""
Dashboard Page — Complete Storage Intelligence Overview for C:\\, D:\\, and Combined Drives.
Clearly distinguishes Estimated (OS Volume), Scanned, and Indexed statistics.
"""

from __future__ import annotations

import datetime
import os
from typing import Dict, List, Optional

from config.settings import SettingsManager
from core.disk_analyzer import DiskAnalysisResult, DiskAnalyzer
from core.drive_manager import DriveInfo, DriveManager
from database.database import LocalDatabase
from database.index_manager import IndexManager
from resources.icons.icon_provider import format_bytes
from ui.components.charts import CategoryBreakdownChart, StorageDonutWidget
from ui.components.stat_card import StatCard
from ui.qt_compat import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Signal,
)
from workers.analysis_worker import DiskAnalysisWorker


class DashboardPage(QWidget):
    """Main storage intelligence dashboard with real drive metrics and visual charts."""

    inspect_file_requested = Signal(str)

    def __init__(
        self,
        drive_mgr: DriveManager,
        settings_mgr: SettingsManager,
        db: LocalDatabase,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.drive_mgr = drive_mgr
        self.settings_mgr = settings_mgr
        self.db = db
        self.idx_mgr = IndexManager(db, settings_mgr)
        self.analyzer = DiskAnalyzer(settings_mgr)
        self.drives: List[DriveInfo] = []
        self.active_mount: str = ""
        self.scan_cache: Dict[str, DiskAnalysisResult] = {}
        self.worker: Optional[DiskAnalysisWorker] = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(14)

        # Header Row
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("Storage Intelligence Dashboard")
        title_lbl.setObjectName("PageTitle")
        self.subtitle_lbl = QLabel(
            "Real-time volume capacity, indexed metrics, and deep filesystem breakdowns across C:\\ and D:\\"
        )
        self.subtitle_lbl.setObjectName("PageSubtitle")
        title_box.addWidget(title_lbl)
        title_box.addWidget(self.subtitle_lbl)

        self.drive_selector = QComboBox()
        self.drive_selector.setMinimumWidth(220)
        self.drive_selector.currentIndexChanged.connect(self._on_drive_switched)

        self.scan_btn = QPushButton("Scan Active Drive Now")
        self.scan_btn.setObjectName("PrimaryButton")
        self.scan_btn.clicked.connect(self.start_live_scan)

        self.cancel_btn = QPushButton("Cancel Scan")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_live_scan)

        header_row.addLayout(title_box, 1)
        header_row.addWidget(self.drive_selector)
        header_row.addWidget(self.scan_btn)
        header_row.addWidget(self.cancel_btn)
        root_layout.addLayout(header_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        # KPI Cards Row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.card_capacity = StatCard("Total Capacity", "0 GB", "Volume Size", "#6366F1")
        self.card_used = StatCard("Used Storage", "0 GB", "0% Used", "#06B6D4")
        self.card_free = StatCard("Available Free", "0 GB", "Ready", "#10B981")
        self.card_counts = StatCard("Files & Folders", "Not scanned", "Source: Estimated", "#F59E0B")
        self.card_index = StatCard("SQLite Index Status", "Checking...", "Last Scan: Never", "#8B5CF6")

        for c in (
            self.card_capacity,
            self.card_used,
            self.card_free,
            self.card_counts,
            self.card_index,
        ):
            cards_row.addWidget(c, 1)
        root_layout.addLayout(cards_row)

        # Charts Grid (Donut + Category + Extension + File Age)
        charts_grid = QGridLayout()
        charts_grid.setSpacing(12)

        self.donut_chart = StorageDonutWidget("Drive Capacity Usage")
        self.cat_chart = CategoryBreakdownChart("Storage Breakdown by Category")
        self.ext_chart = CategoryBreakdownChart("Top Extensions by Storage")
        self.age_chart = CategoryBreakdownChart("File Age Distribution (Count)")

        charts_grid.addWidget(self.donut_chart, 0, 0)
        charts_grid.addWidget(self.cat_chart, 0, 1)
        charts_grid.addWidget(self.ext_chart, 1, 0)
        charts_grid.addWidget(self.age_chart, 1, 1)
        root_layout.addLayout(charts_grid, 1)

        # Bottom Tables: Largest Folders & Largest Files
        tables_row = QHBoxLayout()
        tables_row.setSpacing(12)

        folders_frame = QFrame()
        folders_frame.setObjectName("SurfaceCard")
        fl = QVBoxLayout(folders_frame)
        fl.addWidget(QLabel("Largest Scanned Folders"))
        self.top_folders_table = QTableWidget(0, 3)
        self.top_folders_table.setHorizontalHeaderLabels(["Folder", "Size", "Full Path"])
        self.top_folders_table.horizontalHeader().setStretchLastSection(True)
        fl.addWidget(self.top_folders_table)

        files_frame = QFrame()
        files_frame.setObjectName("SurfaceCard")
        fil = QVBoxLayout(files_frame)
        fil.addWidget(QLabel("Largest Scanned Files (Double-click to Inspect)"))
        self.top_files_table = QTableWidget(0, 3)
        self.top_files_table.setHorizontalHeaderLabels(["Filename", "Size", "Full Path"])
        self.top_files_table.horizontalHeader().setStretchLastSection(True)
        self.top_files_table.itemDoubleClicked.connect(self._on_file_double_clicked)
        fil.addWidget(self.top_files_table)

        tables_row.addWidget(folders_frame, 1)
        tables_row.addWidget(files_frame, 1)
        root_layout.addLayout(tables_row, 1)

        self.refresh_drives()

    def refresh_drives(self) -> None:
        """Detect real drives and populate selector."""
        self.drives = self.drive_mgr.detect_drives()
        self.drive_selector.clear()
        for d in self.drives:
            self.drive_selector.addItem(f"{d.name} [{d.mountpoint}]")
        if len(self.drives) > 1:
            self.drive_selector.addItem("Combined Analysis (All Drives)")
        if self.drives:
            self.active_mount = self.drives[0].mountpoint
            self._update_display_for_mount(self.active_mount)

    def set_active_drive(self, mountpoint: str) -> None:
        if mountpoint == "ALL":
            if len(self.drives) > 1:
                self.drive_selector.blockSignals(True)
                self.drive_selector.setCurrentIndex(len(self.drives))
                self.drive_selector.blockSignals(False)
            self._update_combined_display()
            return
        for idx, d in enumerate(self.drives):
            if os.path.normcase(d.mountpoint) == os.path.normcase(mountpoint):
                self.drive_selector.blockSignals(True)
                self.drive_selector.setCurrentIndex(idx)
                self.drive_selector.blockSignals(False)
                break
        self.active_mount = mountpoint
        self._update_display_for_mount(mountpoint)

    def _on_drive_switched(self, idx: int) -> None:
        if idx < 0:
            return
        if idx < len(self.drives):
            self.active_mount = self.drives[idx].mountpoint
            self._update_display_for_mount(self.active_mount)
        else:
            self._update_combined_display()

    def _update_display_for_mount(self, mountpoint: str) -> None:
        info = self.drive_mgr.get_drive_info(mountpoint)
        if not info:
            return

        self.card_capacity.update_metric(f"{info.total_gb:.2f} GB", f"{info.fstype} • {info.mountpoint}")
        self.card_used.update_metric(f"{info.used_gb:.2f} GB", f"{info.percent_used:.1f}% Used (OS Volume)")
        self.card_free.update_metric(f"{info.free_gb:.2f} GB", f"{100.0 - info.percent_used:.1f}% Available")
        self.donut_chart.set_usage(info.used_bytes, info.total_bytes, f"[{info.mountpoint}] ")

        idx_stats = self.idx_mgr.get_index_stats(mountpoint)
        scanned = self.scan_cache.get(mountpoint)

        if scanned:
            ts_str = datetime.datetime.fromtimestamp(scanned.completed_at).strftime("%H:%M:%S")
            self.card_counts.update_metric(
                f"{scanned.total_files:,} files",
                f"{scanned.total_folders:,} folders • Source: Scanned ({ts_str})",
            )
            self.cat_chart.set_data(scanned.category_bytes, is_bytes=True)
            self.ext_chart.set_data(scanned.extension_bytes, is_bytes=True)
            self._populate_tables(scanned)
        elif idx_stats["available"] and idx_stats["files_count"] > 0:
            last_t = idx_stats["last_scan_time"]
            ts_str = (
                datetime.datetime.fromtimestamp(last_t).strftime("%Y-%m-%d %H:%M")
                if last_t
                else "Indexed"
            )
            self.card_counts.update_metric(
                f"{idx_stats['files_count']:,} files",
                f"{idx_stats['folders_count']:,} folders • Source: Indexed ({ts_str})",
            )
        else:
            self.card_counts.update_metric(
                "Unscanned",
                "Source: Estimated OS Capacity Only",
            )
        if not scanned:
            self.cat_chart.set_data({}, is_bytes=True)
            self.ext_chart.set_data({}, is_bytes=True)
            self.age_chart.set_data({}, is_bytes=False)
            self.top_folders_table.setRowCount(0)
            self.top_files_table.setRowCount(0)

        if self.db.is_available:
            total_idx = self.idx_mgr.get_index_stats()
            self.card_index.update_metric(
                "Enabled (SQLite)",
                f"{total_idx['files_count']:,} total indexed records",
            )
        else:
            self.card_index.update_metric("Disabled / Direct Mode", "Operating 100% database-free")

    def _update_combined_display(self) -> None:
        comb = self.drive_mgr.get_combined_summary(self.drives)
        tot = int(comb["total_bytes"])
        used = int(comb["used_bytes"])
        free = int(comb["free_bytes"])
        pct = float(comb["percent_used"])
        self.card_capacity.update_metric(format_bytes(tot), f"Combined ({comb['drive_count']} Drives)")
        self.card_used.update_metric(format_bytes(used), f"{pct:.1f}% Combined Used")
        self.card_free.update_metric(format_bytes(free), "Combined Available")
        self.donut_chart.set_usage(used, tot, "[All Drives] ")

    def start_live_scan(self) -> None:
        target = self.active_mount or (self.drives[0].mountpoint if self.drives else ".")
        if self.worker and self.worker.isRunning():
            return
        self.progress_bar.setVisible(True)
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.worker = DiskAnalysisWorker(
            target,
            large_threshold_bytes=10 * 1024 * 1024,
            settings_mgr=self.settings_mgr,
            parent=self,
        )
        self.worker.progress.connect(
            lambda cnt, cur: self.subtitle_lbl.setText(f"Scanning ({cnt:,} items): {cur[:75]}")
        )
        self.worker.completed.connect(self._on_scan_finished)
        self.worker.start()

    def cancel_live_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def apply_analysis_result(self, res: DiskAnalysisResult) -> None:
        """Directly apply a DiskAnalysisResult (used by worker callback and tests)."""
        self.scan_cache[res.root_path] = res
        self.active_mount = res.root_path
        self._update_display_for_mount(res.root_path)

        # Compute age distribution from top files + old files sample
        now = datetime.datetime.now().timestamp()
        age_buckets = {"< 7 Days": 0, "7–30 Days": 0, "1–6 Months": 0, "> 6 Months": 0}
        for f in res.top_files:
            days = max(0.0, (now - f.mtime) / 86400.0)
            if days < 7:
                age_buckets["< 7 Days"] += 1
            elif days < 30:
                age_buckets["7–30 Days"] += 1
            elif days < 180:
                age_buckets["1–6 Months"] += 1
            else:
                age_buckets["> 6 Months"] += 1
        self.age_chart.set_data(age_buckets, is_bytes=False)

    def _on_scan_finished(self, res: DiskAnalysisResult) -> None:
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        status = "Cancelled" if res.cancelled else "Completed"
        self.subtitle_lbl.setText(
            f"Scan {status}: {res.total_files:,} files, {res.total_folders:,} folders ({format_bytes(res.total_bytes)})"
        )
        self.apply_analysis_result(res)

    def _populate_tables(self, res: DiskAnalysisResult) -> None:
        self.top_folders_table.setRowCount(min(15, len(res.top_folders)))
        for r, fld in enumerate(res.top_folders[:15]):
            self.top_folders_table.setItem(r, 0, QTableWidgetItem(f"📁 {fld.name}"))
            self.top_folders_table.setItem(r, 1, QTableWidgetItem(format_bytes(fld.total_bytes)))
            self.top_folders_table.setItem(r, 2, QTableWidgetItem(fld.path))

        self.top_files_table.setRowCount(min(15, len(res.top_files)))
        for r, fe in enumerate(res.top_files[:15]):
            self.top_files_table.setItem(r, 0, QTableWidgetItem(fe.name))
            self.top_files_table.setItem(r, 1, QTableWidgetItem(format_bytes(fe.size)))
            path_item = QTableWidgetItem(fe.path)
            self.top_files_table.setItem(r, 2, path_item)

    def _on_file_double_clicked(self, item: QTableWidgetItem) -> None:
        row = self.top_files_table.currentRow()
        path_item = self.top_files_table.item(row, 2)
        if path_item:
            self.inspect_file_requested.emit(path_item.text())
