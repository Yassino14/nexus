"""
NEXUS FILES Main Application Window.
Integrates the permanent 12-module sidebar, global top search/drive bar,
and all 12 functional modules inside a cohesive dark charcoal desktop workspace.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from config.settings import SettingsManager
from core.activity_monitor import ActivityMonitor
from core.drive_manager import DriveManager
from core.file_operations import FileOperationsManager
from database.database import LocalDatabase
from database.index_manager import IndexManager
from ui.components.sidebar import SidebarNavigation
from ui.components.topbar import TopNavigationBar
from ui.pages.activity import RecentActivityPage
from ui.pages.comparison import FolderComparisonPage
from ui.pages.dashboard import DashboardPage
from ui.pages.disk_analyzer import DiskAnalyzerPage
from ui.pages.duplicates import DuplicateFinderPage
from ui.pages.explorer import FileExplorerPage
from ui.pages.inspector import FileInspectorPage
from ui.pages.large_files import LargeFilesPage
from ui.pages.organizer import SmartOrganizerPage
from ui.pages.projects import ProjectFinderPage
from ui.pages.search import GlobalSearchPage
from ui.pages.settings import SettingsPage
from ui.qt_compat import (
    PYSIDE6_AVAILABLE,
    QApplication,
    QHBoxLayout,
    QIcon,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from workers.scan_worker import ScanWorker


def get_resource_path(relative_path: str) -> Path:
    """Resolve resource path both in source mode and PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative_path


class NexusMainWindow(QMainWindow):
    """Primary desktop window coordinating all 12 NEXUS FILES modules."""

    def __init__(
        self,
        settings_mgr: Optional[SettingsManager] = None,
        db: Optional[LocalDatabase] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(
            "NEXUS FILES — Advanced Windows File Explorer, Search Engine & Disk Analyzer"
        )
        if hasattr(self, "setMinimumSize"):
            self.setMinimumSize(880, 500)
        self._apply_responsive_geometry()

        self.settings_mgr = settings_mgr or SettingsManager()
        self.db = db or LocalDatabase(
            self.settings_mgr.settings.database_location,
            enabled=self.settings_mgr.settings.database_enabled,
        )
        self.drive_mgr = DriveManager()
        self.ops = FileOperationsManager(self.settings_mgr)
        self.monitor = ActivityMonitor()
        self.index_worker: Optional[ScanWorker] = None

        # Apply Application Icon & QSS Dark Charcoal Theme
        icon_path = get_resource_path("resources/icons/nexus_app_icon.ico")
        if not icon_path.exists():
            icon_path = get_resource_path("resources/icons/nexus_files.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        qss_path = get_resource_path("resources/styles/dark_theme.qss")
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

        central = QWidget(self)
        self.setCentralWidget(central)
        outer_layout = QHBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Left Permanent Sidebar (12 modules)
        self.sidebar = SidebarNavigation(self)
        outer_layout.addWidget(self.sidebar)

        # Right Workspace Column (TopBar + Stacked Pages)
        right_col = QWidget(self)
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.topbar = TopNavigationBar(self)
        self.topbar.set_drives(self.drive_mgr.detect_drives())
        right_layout.addWidget(self.topbar)

        self.stack = QStackedWidget(self)
        right_layout.addWidget(self.stack, 1)
        outer_layout.addWidget(right_col, 1)

        # Instantiate all 12 pages
        default_dir = self.settings_mgr.settings.default_drive
        self.page_dashboard = DashboardPage(self.drive_mgr, self.settings_mgr, self.db, self)
        self.page_explorer = FileExplorerPage(self.ops, self.settings_mgr, self)
        self.page_search = GlobalSearchPage(self.db, self.ops, self.settings_mgr, self)
        self.page_analyzer = DiskAnalyzerPage(self.settings_mgr, self)
        self.page_duplicates = DuplicateFinderPage(self.ops, self.settings_mgr, self)
        self.page_large_files = LargeFilesPage(self.db, self.ops, self.settings_mgr, self)
        self.page_organizer = SmartOrganizerPage(self.ops, default_dir, self)
        self.page_inspector = FileInspectorPage(self)
        self.page_projects = ProjectFinderPage(self.settings_mgr, self)
        self.page_activity = RecentActivityPage(self.monitor, self.settings_mgr, self)
        self.page_comparison = FolderComparisonPage(default_dir, self)
        self.page_settings = SettingsPage(self.settings_mgr, self.db, self)

        self.pages = [
            self.page_dashboard,
            self.page_explorer,
            self.page_search,
            self.page_analyzer,
            self.page_duplicates,
            self.page_large_files,
            self.page_organizer,
            self.page_inspector,
            self.page_projects,
            self.page_activity,
            self.page_comparison,
            self.page_settings,
        ]
        for p in self.pages:
            self.stack.addWidget(p)

        # Cross-page navigation signals
        self.sidebar.page_selected.connect(self._on_sidebar_nav)
        self.topbar.global_search_triggered.connect(self.trigger_global_search)
        self.topbar.drive_changed.connect(self._on_global_drive_changed)
        self.topbar.quick_index_requested.connect(self.start_background_indexing)

        self.page_dashboard.inspect_file_requested.connect(self.open_in_inspector)
        self.page_explorer.inspect_file_requested.connect(self.open_in_inspector)
        self.page_search.inspect_file_requested.connect(self.open_in_inspector)
        self.page_analyzer.inspect_file_requested.connect(self.open_in_inspector)
        self.page_large_files.inspect_file_requested.connect(self.open_in_inspector)
        self.page_search.open_in_explorer_requested.connect(self.open_folder_in_explorer)
        self.page_duplicates.open_in_explorer_requested.connect(self.open_folder_in_explorer)
        self.page_projects.open_in_explorer_requested.connect(self.open_folder_in_explorer)
        self.page_settings.settings_saved.connect(self._on_settings_saved)

        if self.settings_mgr.settings.background_monitoring:
            if self.monitor.start([default_dir]):
                self.page_activity.toggle_btn.setText("Stop Monitoring")
                self.page_activity.status_lbl.setText(f"Actively monitoring {default_dir}...")

        self._refresh_index_badge()
        self.statusBar().showMessage("NEXUS FILES ready — 100% Local Offline Mode.")

    def _apply_responsive_geometry(self) -> None:
        """Size and center the window dynamically based on the active monitor's available geometry."""
        if PYSIDE6_AVAILABLE and hasattr(QApplication, "primaryScreen"):
            screen = QApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                target_w = min(1440, max(880, int(avail.width() * 0.94)))
                target_h = min(900, max(500, int(avail.height() * 0.92)))
                self.resize(target_w, target_h)
                if hasattr(self, "move"):
                    x = avail.x() + max(0, (avail.width() - target_w) // 2)
                    y = avail.y() + max(0, (avail.height() - target_h) // 2)
                    self.move(x, y)
                return
        self.resize(1280, 700)

    def _on_sidebar_nav(self, index: int, name: str) -> None:
        self.stack.setCurrentIndex(index)
        self.statusBar().showMessage(f"Module: {name}")

    def trigger_global_search(self, query_text: str) -> None:
        self.sidebar.select_page(2)  # Switch to Global Search page
        self.page_search.query_input.setText(query_text)
        self.page_search.run_search()

    def open_in_inspector(self, file_path: str) -> None:
        self.sidebar.select_page(7)  # Switch to File Inspector page
        self.page_inspector.inspect_file(file_path)

    def open_folder_in_explorer(self, folder_path: str) -> None:
        self.sidebar.select_page(1)  # Switch to File Explorer page
        tab = self.page_explorer.active_tab()
        if tab:
            tab.navigate_to(folder_path)

    def _on_global_drive_changed(self, mountpoint: str) -> None:
        self.page_dashboard.set_active_drive(mountpoint)
        self.page_search.scope_input.setText(mountpoint)
        self.page_large_files.root_input.setText(mountpoint)
        if mountpoint != "ALL":
            self.page_analyzer.path_input.setText(mountpoint)
            self.page_duplicates.path_input.setText(mountpoint)
            self.page_projects.root_input.setText(mountpoint)

    def _on_settings_saved(self) -> None:
        s = self.settings_mgr.settings
        self.page_explorer.hidden_chk.setChecked(s.show_hidden_files)
        self.page_search.mode_combo.setCurrentText(s.default_search_mode)
        self._refresh_index_badge()
        self.page_dashboard.refresh_drives()
        self.statusBar().showMessage("Settings updated.")

    def closeEvent(self, event: object) -> None:
        self.monitor.stop()
        for worker in (
            self.index_worker,
            self.page_dashboard.worker,
            self.page_search.worker,
            self.page_analyzer.worker,
            self.page_duplicates.worker,
            getattr(self.page_large_files, "worker", None),
            getattr(self.page_projects, "worker", None),
        ):
            if worker is not None and worker.isRunning():
                worker.cancel()
                if not worker.wait(800) and hasattr(worker, "terminate"):
                    worker.terminate()
                    worker.wait(200)
        if hasattr(QMainWindow, "closeEvent"):
            super().closeEvent(event)  # type: ignore[arg-type]

    def start_background_indexing(self, root_path: str) -> None:
        target = root_path if root_path and root_path != "ALL" else self.settings_mgr.settings.default_drive
        if self.index_worker and self.index_worker.isRunning():
            return
        self.topbar.set_index_status("Indexing...", active=False)
        self.index_worker = ScanWorker(
            target,
            self.settings_mgr,
            db=self.db,
            update_index=True,
            incremental=True,
            parent=self,
        )
        self.index_worker.progress.connect(
            lambda f, d, p: self.statusBar().showMessage(f"Indexing: {f:,} files, {d:,} folders ({p[:65]})")
        )
        self.index_worker.completed.connect(lambda _: self._on_indexing_completed())
        self.index_worker.start()

    def _on_indexing_completed(self) -> None:
        self._refresh_index_badge()
        self.page_dashboard.refresh_drives()
        self.statusBar().showMessage("SQLite index updated.")

    def _refresh_index_badge(self) -> None:
        if not self.db.is_available:
            self.topbar.set_index_status("Index: Off (Direct Mode)", active=False)
            return
        stats = IndexManager(self.db, self.settings_mgr).get_index_stats()
        self.topbar.set_index_status(f"Indexed: {stats['files_count']:,} files", active=True)
