"""
Project Finder Page — Programming Project Discovery Engine across C:\\ and D:\\.
Detects Python, JavaScript/TypeScript, Java, .NET/C#, Rust, Go, and Git repositories
while ignoring nested build/virtualenv directories.
"""

from __future__ import annotations

import datetime
import subprocess
from typing import List, Optional

from config.settings import SettingsManager
from core.project_detector import DetectedProject, ProjectDetector
from ui.qt_compat import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QThread,
    QVBoxLayout,
    QWidget,
    Signal,
)


class ProjectScanWorker(QThread):
    """Background worker for scanning programming projects without freezing the UI."""

    completed = Signal(list)
    error = Signal(str)

    def __init__(self, roots: List[str], settings_mgr: SettingsManager, parent: object = None) -> None:
        super().__init__(parent)
        self.roots = roots
        self.settings_mgr = settings_mgr
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            detector = ProjectDetector(self.settings_mgr)
            res = detector.scan_for_projects(self.roots, cancel_check=self.is_cancelled)
            if not self._cancelled:
                self.completed.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class ProjectFinderPage(QWidget):
    """Discovers software engineering projects and Git repositories."""

    open_in_explorer_requested = Signal(str)

    def __init__(
        self,
        settings_mgr: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_mgr = settings_mgr
        self.detector = ProjectDetector(settings_mgr)
        self.projects: List[DetectedProject] = []
        self.worker: Optional[ProjectScanWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Programming Project Finder")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Automatically discover Python, JavaScript/Node.js, Java, .NET/C#, Rust, Go, and Git projects "
            "without nested node_modules or virtualenv duplicates."
        )
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        ctrl = QHBoxLayout()
        self.root_input = QLineEdit(self.settings_mgr.settings.default_drive)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_root)

        self.scan_btn = QPushButton("Scan for Projects")
        self.scan_btn.setObjectName("PrimaryButton")
        self.scan_btn.clicked.connect(lambda: self.scan_projects(synchronous=False))

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_scan)

        self.open_folder_btn = QPushButton("Open Project Folder")
        self.open_folder_btn.clicked.connect(self.open_selected_folder)

        self.open_editor_btn = QPushButton("Open in Code Editor")
        self.open_editor_btn.clicked.connect(self.open_in_editor)

        ctrl.addWidget(QLabel("Search Root:"))
        ctrl.addWidget(self.root_input, 1)
        ctrl.addWidget(self.browse_btn)
        ctrl.addWidget(self.scan_btn)
        ctrl.addWidget(self.cancel_btn)
        ctrl.addWidget(self.open_folder_btn)
        ctrl.addWidget(self.open_editor_btn)
        layout.addLayout(ctrl)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Project Name",
            "Technology Stack",
            "Git Branch",
            "Config & Marker Files",
            "Project Location",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda _: self.open_selected_folder())
        layout.addWidget(self.table, 1)

        self.status_lbl = QLabel("Click 'Scan for Projects' to discover repositories.")
        self.status_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.status_lbl)

    def _browse_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Root Folder to Scan for Projects")
        if chosen:
            self.root_input.setText(chosen)

    def scan_projects(self, synchronous: bool = True) -> List[DetectedProject]:
        root = self.root_input.text().strip() or "."
        if synchronous:
            res = self.detector.scan_for_projects([root])
            self._apply_projects(res)
            return res

        if self.worker and self.worker.isRunning():
            self.worker.cancel()

        self.scan_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.status_lbl.setText(f"Scanning {root} for software projects...")
        self.worker = ProjectScanWorker([root], self.settings_mgr, self)
        self.worker.completed.connect(self._apply_projects)
        self.worker.start()
        return []

    def cancel_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.scan_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)
            self.status_lbl.setText("Project scan cancelled.")

    def _apply_projects(self, found: List[DetectedProject]) -> None:
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.projects = found
        self.table.setRowCount(len(self.projects))
        for r, proj in enumerate(self.projects):
            git_txt = f"⎇ {proj.git_branch}" if proj.git_branch else ("Git" if proj.has_git else "—")
            self.table.setItem(r, 0, QTableWidgetItem(f"⌘  {proj.name}"))
            self.table.setItem(r, 1, QTableWidgetItem(proj.project_type))
            self.table.setItem(r, 2, QTableWidgetItem(git_txt))
            self.table.setItem(r, 3, QTableWidgetItem(", ".join(proj.config_files)))
            self.table.setItem(r, 4, QTableWidgetItem(proj.location))

        self.status_lbl.setText(f"Discovered {len(self.projects)} programming project(s).")

    def open_selected_folder(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.projects):
            self.open_in_explorer_requested.emit(self.projects[row].location)

    def open_in_editor(self) -> bool:
        row = self.table.currentRow()
        if not (0 <= row < len(self.projects)):
            return False
        loc = self.projects[row].location
        editor = self.settings_mgr.settings.preferred_editor or "code"
        try:
            subprocess.Popen([editor, loc])
            return True
        except Exception:
            self.open_in_explorer_requested.emit(loc)
            return False
