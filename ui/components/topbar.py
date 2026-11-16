"""
Global Top Navigation Bar with quick drive selector, index status indicator,
and instant Global Search bar.
"""

from __future__ import annotations

from typing import List

from core.drive_manager import DriveInfo
from ui.qt_compat import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    Signal,
)


class TopNavigationBar(QFrame):
    """Top bar providing global search, active drive selector, and index status badge."""

    global_search_triggered = Signal(str)
    drive_changed = Signal(str)
    quick_index_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBarFrame")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        drive_lbl = QLabel("Active Drive:")
        drive_lbl.setObjectName("PageSubtitle")
        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(140)
        self.drive_combo.currentTextChanged.connect(self._on_drive_combo_changed)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Global Search across C:\\ and D:\\ (Press Enter or Ctrl+F)..."
        )
        self.search_input.returnPressed.connect(self._emit_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("PrimaryButton")
        self.search_btn.clicked.connect(self._emit_search)

        self.index_badge = QLabel("Index: Ready")
        self.index_badge.setStyleSheet(
            "background-color: #161F2E; color: #38BDF8; border: 1px solid #1E3A8A; "
            "border-radius: 10px; padding: 4px 10px; font-size: 11px;"
        )

        self.index_now_btn = QPushButton("Update Index")
        self.index_now_btn.clicked.connect(
            lambda: self.quick_index_requested.emit(self.current_drive_mount())
        )

        layout.addWidget(drive_lbl)
        layout.addWidget(self.drive_combo)
        layout.addWidget(self.search_input, 1)
        layout.addWidget(self.search_btn)
        layout.addWidget(self.index_badge)
        layout.addWidget(self.index_now_btn)

        self._drive_map: dict[str, str] = {}

    def set_drives(self, drives: List[DriveInfo]) -> None:
        self.drive_combo.clear()
        self._drive_map.clear()
        for d in drives:
            label = f"{d.mountpoint} — {d.free_gb:.1f} GB free / {d.total_gb:.1f} GB"
            self._drive_map[label] = d.mountpoint
            self.drive_combo.addItem(label)
        if len(drives) > 1:
            all_lbl = "All Drives (Combined C: + D:)"
            self._drive_map[all_lbl] = "ALL"
            self.drive_combo.addItem(all_lbl)

    def current_drive_mount(self) -> str:
        txt = self.drive_combo.currentText()
        return self._drive_map.get(txt, txt.split(" — ")[0] if txt else "")

    def set_index_status(self, status_text: str, active: bool = True) -> None:
        self.index_badge.setText(status_text)
        color = "#34D399" if active else "#FBBF24"
        self.index_badge.setStyleSheet(
            f"background-color: #161F2E; color: {color}; border: 1px solid #334155; "
            "border-radius: 10px; padding: 4px 10px; font-size: 11px;"
        )

    def _emit_search(self) -> None:
        q = self.search_input.text().strip()
        self.global_search_triggered.emit(q)

    def _on_drive_combo_changed(self, text: str) -> None:
        mount = self._drive_map.get(text, "")
        if mount:
            self.drive_changed.emit(mount)
