"""
Recent File Activity Page — Optional Resource-Efficient Filesystem Monitor.
Tracks Created, Modified, Renamed, Deleted, and New Folders with filtering.
"""

from __future__ import annotations

import datetime
from typing import List

from config.settings import SettingsManager
from core.activity_monitor import ActivityEvent, ActivityMonitor
from ui.qt_compat import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class RecentActivityPage(QWidget):
    """Real-time and snapshot-based filesystem activity monitor."""

    def __init__(
        self,
        monitor: ActivityMonitor,
        settings_mgr: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.monitor = monitor
        self.settings_mgr = settings_mgr

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Recent File Activity Monitor")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Optional lightweight filesystem watcher tracking new, modified, and renamed files. "
            "NEXUS FILES remains 100% functional when monitoring is turned off."
        )
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        ctrl = QHBoxLayout()
        self.watch_path_input = QLineEdit(self.settings_mgr.settings.default_drive)
        self.ext_filter_input = QLineEdit()
        self.ext_filter_input.setPlaceholderText("Filter ext (e.g. .py)")
        self.ext_filter_input.setMaximumWidth(150)
        self.ext_filter_input.textChanged.connect(lambda _: self.refresh_table())

        self.toggle_btn = QPushButton("Start Monitoring")
        self.toggle_btn.setObjectName("PrimaryButton")
        self.toggle_btn.clicked.connect(self.toggle_monitoring)

        self.poll_btn = QPushButton("Poll Changes Now")
        self.poll_btn.clicked.connect(self.poll_and_refresh)

        ctrl.addWidget(QLabel("Watch Folder:"))
        ctrl.addWidget(self.watch_path_input, 1)
        ctrl.addWidget(self.ext_filter_input)
        ctrl.addWidget(self.toggle_btn)
        ctrl.addWidget(self.poll_btn)
        layout.addLayout(ctrl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Event Type", "Extension", "File / Folder Path"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.status_lbl = QLabel("Monitoring is currently stopped (zero background CPU usage).")
        self.status_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.status_lbl)

    def toggle_monitoring(self) -> bool:
        if self.monitor.is_running:
            self.monitor.stop()
            self.toggle_btn.setText("Start Monitoring")
            self.status_lbl.setText("Monitoring stopped.")
            return False
        target = self.watch_path_input.text().strip() or "."
        ok = self.monitor.start([target])
        if ok:
            self.toggle_btn.setText("Stop Monitoring")
            self.status_lbl.setText(f"Actively monitoring {target}...")
        return ok

    def poll_and_refresh(self) -> List[ActivityEvent]:
        self.monitor.poll_once()
        return self.refresh_table()

    def refresh_table(self) -> List[ActivityEvent]:
        events = self.monitor.get_filtered_events(
            extension_filter=self.ext_filter_input.text().strip()
        )
        self.table.setRowCount(len(events))
        for r, ev in enumerate(events):
            ts = datetime.datetime.fromtimestamp(ev.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            path_txt = f"{ev.path} → {ev.dest_path}" if ev.dest_path else ev.path
            self.table.setItem(r, 0, QTableWidgetItem(ts))
            self.table.setItem(r, 1, QTableWidgetItem(ev.event_type))
            self.table.setItem(r, 2, QTableWidgetItem(ev.extension or ("Folder" if ev.is_dir else "—")))
            self.table.setItem(r, 3, QTableWidgetItem(path_txt))
        return events
