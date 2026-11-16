"""
Settings Page — Comprehensive Offline Configuration & SQLite Index Administration.
"""

from __future__ import annotations

from pathlib import Path

from config.settings import SettingsManager
from database.database import LocalDatabase
from ui.qt_compat import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    Signal,
)


class SettingsPage(QWidget):
    """Persists all user preferences and manages the optional SQLite database."""

    settings_saved = Signal()

    def __init__(
        self,
        settings_mgr: SettingsManager,
        db: LocalDatabase,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_mgr = settings_mgr
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Application & Indexing Settings")
        title.setObjectName("PageTitle")
        sub = QLabel("All settings are stored 100% locally in JSON. No telemetry, accounts, or cloud sync.")
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        card = QFrame()
        card.setObjectName("SurfaceCard")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        s = self.settings_mgr.settings

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Charcoal (Linear)", "Midnight Slate (Raycast)", "Windows 11 Dark"])
        self.theme_combo.setCurrentText(s.theme)

        self.accent_combo = QComboBox()
        self.accent_combo.addItems(["#6366F1 (Indigo)", "#06B6D4 (Cyan)", "#10B981 (Emerald)", "#3B82F6 (Blue)"])
        self._select_accent(s.accent_color)

        self.default_drive_input = QLineEdit(s.default_drive)

        self.view_combo = QComboBox()
        self.view_combo.addItems(["Detailed", "List", "Grid"])
        self.view_combo.setCurrentText(s.default_folder_view)

        self.search_mode_combo = QComboBox()
        self.search_mode_combo.addItems(["Direct", "Indexed"])
        self.search_mode_combo.setCurrentText(s.default_search_mode)

        self.db_enabled_chk = QCheckBox("Enable Optional SQLite Local Index")
        self.db_enabled_chk.setChecked(s.database_enabled)

        self.db_location_input = QLineEdit(s.database_location)

        self.content_idx_chk = QCheckBox("Enable Optional Text Content Indexing (disabled by default)")
        self.content_idx_chk.setChecked(s.content_indexing_enabled)

        self.hidden_chk = QCheckBox("Show Hidden Files and Folders")
        self.hidden_chk.setChecked(s.show_hidden_files)

        self.monitor_chk = QCheckBox("Enable Background Filesystem Monitoring on Startup")
        self.monitor_chk.setChecked(s.background_monitoring)

        self.confirm_batch_chk = QCheckBox("Always Confirm Batch File Operations & Deletions")
        self.confirm_batch_chk.setChecked(s.confirm_batch_operations)

        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(1000, 10_000_000)
        self.max_files_spin.setValue(s.indexing_max_files)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(s.max_worker_threads)

        self.backup_input = QLineEdit(s.default_backup_location)

        self.excluded_edit = QPlainTextEdit("\n".join(s.excluded_directories))
        self.excluded_edit.setFixedHeight(90)

        form.addRow("UI Theme:", self.theme_combo)
        form.addRow("Accent Color:", self.accent_combo)
        form.addRow("Default Drive / Path:", self.default_drive_input)
        form.addRow("Default Explorer View:", self.view_combo)
        form.addRow("Default Search Mode:", self.search_mode_combo)
        form.addRow("SQLite Index:", self.db_enabled_chk)
        form.addRow("Database Location:", self.db_location_input)
        form.addRow("File Content Indexing:", self.content_idx_chk)
        form.addRow("Hidden Files:", self.hidden_chk)
        form.addRow("Activity Monitoring:", self.monitor_chk)
        form.addRow("Safety Confirmations:", self.confirm_batch_chk)
        form.addRow("Max Indexed Files:", self.max_files_spin)
        form.addRow("Max Worker Threads:", self.threads_spin)
        form.addRow("Default Backup Folder:", self.backup_input)
        form.addRow("Excluded Directories (1 per line):", self.excluded_edit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(card)
        layout.addWidget(scroll, 1)

        # Database Maintenance & Save Buttons
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_settings)

        self.integrity_btn = QPushButton("Verify DB Integrity")
        self.integrity_btn.clicked.connect(self.check_db_integrity)

        self.rebuild_btn = QPushButton("Rebuild SQLite Index")
        self.rebuild_btn.clicked.connect(self.rebuild_db)

        self.clear_btn = QPushButton("Clear SQLite Index")
        self.clear_btn.setObjectName("DangerButton")
        self.clear_btn.clicked.connect(self.clear_db)

        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self.reset_defaults)

        for b in (self.save_btn, self.integrity_btn, self.rebuild_btn, self.clear_btn, self.reset_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        self.status_lbl = QLabel("Settings loaded from local configuration.")
        self.status_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.status_lbl)

    def save_settings(self) -> bool:
        s = self.settings_mgr.settings
        s.theme = self.theme_combo.currentText()
        s.accent_color = self.accent_combo.currentText().split(" ")[0]
        s.default_drive = self.default_drive_input.text().strip()
        s.default_folder_view = self.view_combo.currentText()
        s.default_search_mode = self.search_mode_combo.currentText()
        s.database_enabled = self.db_enabled_chk.isChecked()
        s.database_location = self.db_location_input.text().strip()
        s.content_indexing_enabled = self.content_idx_chk.isChecked()
        s.show_hidden_files = self.hidden_chk.isChecked()
        s.background_monitoring = self.monitor_chk.isChecked()
        s.confirm_batch_operations = self.confirm_batch_chk.isChecked()
        s.indexing_max_files = self.max_files_spin.value()
        s.max_worker_threads = self.threads_spin.value()
        s.default_backup_location = self.backup_input.text().strip()
        s.excluded_directories = [
            line.strip() for line in self.excluded_edit.toPlainText().splitlines() if line.strip()
        ]

        ok = self.settings_mgr.save()
        self.db.enabled = s.database_enabled
        if s.database_location:
            self.db.db_path = Path(s.database_location)
        if s.database_enabled:
            self.db.initialize()
        else:
            self.db._healthy = False
        self.status_lbl.setText("Settings saved locally." if ok else "Failed to save settings.")
        self.settings_saved.emit()
        return ok

    def _select_accent(self, accent_hex: str) -> None:
        for idx in range(self.accent_combo.count()):
            if self.accent_combo.itemText(idx).startswith(accent_hex):
                self.accent_combo.setCurrentIndex(idx)
                return

    def _populate_from_settings(self) -> None:
        s = self.settings_mgr.settings
        self.theme_combo.setCurrentText(s.theme)
        self._select_accent(s.accent_color)
        self.default_drive_input.setText(s.default_drive)
        self.view_combo.setCurrentText(s.default_folder_view)
        self.search_mode_combo.setCurrentText(s.default_search_mode)
        self.db_enabled_chk.setChecked(s.database_enabled)
        self.db_location_input.setText(s.database_location)
        self.content_idx_chk.setChecked(s.content_indexing_enabled)
        self.hidden_chk.setChecked(s.show_hidden_files)
        self.monitor_chk.setChecked(s.background_monitoring)
        self.confirm_batch_chk.setChecked(s.confirm_batch_operations)
        self.max_files_spin.setValue(s.indexing_max_files)
        self.threads_spin.setValue(s.max_worker_threads)
        self.backup_input.setText(s.default_backup_location)
        self.excluded_edit.setPlainText("\n".join(s.excluded_directories))

    def check_db_integrity(self) -> bool:
        healthy = self.db.check_integrity()
        self.status_lbl.setText(
            "SQLite Integrity Check: OK (Healthy)" if healthy else "SQLite Integrity Check: Corrupted (Auto-recovering)"
        )
        return healthy

    def rebuild_db(self) -> bool:
        ok = self.db.rebuild()
        self.status_lbl.setText("SQLite database rebuilt cleanly." if ok else "Database rebuild failed.")
        return ok

    def clear_db(self) -> bool:
        ok = self.db.clear_all()
        self.status_lbl.setText("Cleared all indexed records." if ok else "Database clear failed.")
        return ok

    def reset_defaults(self) -> None:
        self.settings_mgr.reset_to_defaults()
        self._populate_from_settings()
        self.settings_saved.emit()
        self.status_lbl.setText("Restored factory default settings.")
