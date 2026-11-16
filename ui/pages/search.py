"""
Global Search Page — Universal Search Engine across C:\\ and D:\\.
Supports Mode A (Indexed SQLite/FTS5) and Mode B (Direct Filesystem Search),
advanced category pills, size/date/content filters, fuzzy matching,
saved searches, search history, and right-click context actions.
"""

from __future__ import annotations

import os
from pathlib import Path
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
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    Qt,
    QTableView,
    QVBoxLayout,
    QWidget,
    Signal,
)
from workers.search_worker import SearchWorker


class GlobalSearchPage(QWidget):
    """Universal Search Engine UI with instant filtering and background worker execution."""

    inspect_file_requested = Signal(str)
    open_in_explorer_requested = Signal(str)

    CATEGORIES = [
        "All",
        "PDFs",
        "Images",
        "Videos",
        "Audio",
        "Documents",
        "Archives",
        "Executables",
        "Programming",
        "Recently Modified",
        "Old Files",
    ]

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

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(12)

        title_lbl = QLabel("Universal Search Engine")
        title_lbl.setObjectName("PageTitle")
        sub_lbl = QLabel(
            "Search across C:\\ and D:\\ using lightning-fast SQLite FTS5 Indexed Mode or Direct Filesystem Mode."
        )
        sub_lbl.setObjectName("PageSubtitle")
        root_layout.addWidget(title_lbl)
        root_layout.addWidget(sub_lbl)

        # Primary Search Controls Card
        search_card = QFrame()
        search_card.setObjectName("SurfaceCard")
        sc_layout = QVBoxLayout(search_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(10)

        top_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter filename, partial match, or pattern...")
        self.query_input.returnPressed.connect(self.run_search)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Direct", "Indexed"])
        self.mode_combo.setCurrentText(self.settings_mgr.settings.default_search_mode)

        default_drv = self.settings_mgr.settings.default_drive
        initial_scope = "ALL" if len(default_drv.strip()) <= 3 else default_drv
        self.scope_input = QLineEdit(initial_scope)
        self.scope_input.setPlaceholderText("ALL, C:\\, D:\\, or folder path")
        self.scope_input.setMaximumWidth(200)

        self.browse_scope_btn = QPushButton("Browse...")
        self.browse_scope_btn.clicked.connect(self._browse_scope)

        self.search_btn = QPushButton("Search Now")
        self.search_btn.setObjectName("PrimaryButton")
        self.search_btn.clicked.connect(self.run_search)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_search)

        self.save_search_btn = QPushButton("★ Save Search")
        self.save_search_btn.clicked.connect(self.save_current_search)

        top_row.addWidget(self.query_input, 1)
        top_row.addWidget(QLabel("Mode:"))
        top_row.addWidget(self.mode_combo)
        top_row.addWidget(QLabel("Scope:"))
        top_row.addWidget(self.scope_input)
        top_row.addWidget(self.browse_scope_btn)
        top_row.addWidget(self.search_btn)
        top_row.addWidget(self.cancel_btn)
        top_row.addWidget(self.save_search_btn)
        sc_layout.addLayout(top_row)

        # Second Row: Advanced Filters
        adv_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.CATEGORIES)

        self.ext_input = QLineEdit()
        self.ext_input.setPlaceholderText("Extensions (e.g. .py, .pdf)")
        self.ext_input.setMaximumWidth(160)

        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(0, 100000)
        self.min_size_spin.setSuffix(" MB min")

        self.content_input = QLineEdit()
        self.content_input.setPlaceholderText("File content contains (optional)...")

        self.exact_chk = QCheckBox("Exact Name")
        self.fuzzy_chk = QCheckBox("Fuzzy Match")
        self.dirs_chk = QCheckBox("Include Folders")
        self.dirs_chk.setChecked(True)

        self.saved_combo = QComboBox()
        self.saved_combo.setMinimumWidth(150)
        self.saved_combo.addItem("Saved Searches...")
        self._refresh_saved_searches()
        self.saved_combo.currentIndexChanged.connect(self._load_saved_search)

        adv_row.addWidget(QLabel("Category:"))
        adv_row.addWidget(self.category_combo)
        adv_row.addWidget(self.ext_input)
        adv_row.addWidget(self.min_size_spin)
        adv_row.addWidget(self.content_input, 1)
        adv_row.addWidget(self.exact_chk)
        adv_row.addWidget(self.fuzzy_chk)
        adv_row.addWidget(self.dirs_chk)
        adv_row.addWidget(self.saved_combo)
        sc_layout.addLayout(adv_row)

        root_layout.addWidget(search_card)

        # Results Table
        self.results_model = VirtualFileTableModel()
        self.results_table = QTableView()
        self.results_table.setModel(self.results_model)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results_table.setSortingEnabled(True)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.doubleClicked.connect(self._on_double_click)
        self.results_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self._show_context_menu)
        root_layout.addWidget(self.results_table, 1)

        # Action Bar for Selected Result
        act_row = QHBoxLayout()
        self.status_lbl = QLabel("Enter a query above to search across your drives.")
        self.status_lbl.setObjectName("PageSubtitle")

        btn_open = QPushButton("Open File")
        btn_open.clicked.connect(self.action_open_selected)
        btn_folder = QPushButton("Open Containing Folder")
        btn_folder.clicked.connect(self.action_open_containing)
        btn_copy_path = QPushButton("Copy Full Path")
        btn_copy_path.clicked.connect(self.action_copy_path)
        btn_inspect = QPushButton("Inspect Properties")
        btn_inspect.clicked.connect(self.action_inspect_selected)
        btn_delete = QPushButton("Delete to Recycle Bin")
        btn_delete.setObjectName("DangerButton")
        btn_delete.clicked.connect(self.action_delete_selected)

        act_row.addWidget(self.status_lbl, 1)
        for b in (btn_open, btn_folder, btn_copy_path, btn_inspect, btn_delete):
            act_row.addWidget(b)
        root_layout.addLayout(act_row)

    def build_query(self) -> SearchQuery:
        exts = [
            e.strip()
            for e in self.ext_input.text().replace(";", ",").split(",")
            if e.strip()
        ]
        min_b = self.min_size_spin.value() * 1024 * 1024 if self.min_size_spin.value() > 0 else None
        scope = self.scope_input.text().strip()
        roots = [scope] if scope and scope != "ALL" else []
        return SearchQuery(
            text=self.query_input.text().strip(),
            exact_match=self.exact_chk.isChecked(),
            fuzzy_match=self.fuzzy_chk.isChecked(),
            search_mode=self.mode_combo.currentText(),
            roots=roots,
            extensions=exts,
            category=self.category_combo.currentText(),
            min_size_bytes=min_b,
            content_query=self.content_input.text().strip(),
            include_dirs=self.dirs_chk.isChecked(),
        )

    def _browse_scope(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Search Folder")
        if chosen:
            self.scope_input.setText(chosen)

    def _show_context_menu(self, pos: object) -> None:
        menu = QMenu(self)
        menu.addAction("Open", self.action_open_selected)
        menu.addAction("Open Containing Folder", self.action_open_containing)
        menu.addAction("Inspect Properties", self.action_inspect_selected)
        menu.addAction("Copy Full Path", self.action_copy_path)
        menu.addSeparator()
        menu.addAction("Delete to Recycle Bin", self.action_delete_selected)
        vp = self.results_table.viewport() if hasattr(self.results_table, "viewport") else self.results_table
        global_pos = vp.mapToGlobal(pos) if hasattr(vp, "mapToGlobal") else pos
        menu.exec(global_pos)  # type: ignore

    def run_search(self, synchronous: bool = False) -> List[ScannedEntry]:
        q = self.build_query()
        if synchronous:
            res = self.engine.search(q)
            self._on_results_ready(res)
            return res

        if self.worker is not None:
            try:
                self.worker.results_ready.disconnect(self._on_results_ready)
                self.worker.partial_results.disconnect(self._on_partial_results)
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.cancel()

        self.search_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.results_model.set_entries([])
        scope_label = ", ".join(q.roots) if q.roots else "All Drives (C: + D:)"
        self.status_lbl.setText(f"Searching {scope_label} ({q.search_mode} mode)...")

        self.worker = SearchWorker(q, self.db, self.settings_mgr, self)
        self.worker.partial_results.connect(self._on_partial_results)
        self.worker.results_ready.connect(self._on_results_ready)
        self.worker.start()
        return []

    def cancel_search(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_lbl.setText(
                f"Search stopped ({self.results_model.rowCount():,} items found so far)."
            )
            self.search_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)

    def _on_partial_results(self, partial: List[ScannedEntry], scanned_count: int, cur_dir: str) -> None:
        self.results_model.set_entries(partial)
        self.status_lbl.setText(
            f"Found {len(partial):,} matches so far (scanned {scanned_count:,} items — {cur_dir[:55]})"
        )

    def _on_results_ready(self, results: List[ScannedEntry]) -> None:
        self.search_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.results_model.set_entries(results)
        tot_size = sum(e.size for e in results if not e.is_dir)
        self.status_lbl.setText(
            f"Found {len(results):,} matching items ({format_bytes(tot_size)} total)"
        )

    def _selected_entry(self) -> Optional[ScannedEntry]:
        rows = self.results_table.selectionModel().selectedRows()
        if rows:
            return self.results_model.get_entry(rows[0].row())
        return self.results_model.get_entry(0)

    def _on_double_click(self, index: object) -> None:
        row = getattr(index, "row", lambda: 0)()
        entry = self.results_model.get_entry(row)
        if entry:
            self.inspect_file_requested.emit(entry.path)

    def action_open_selected(self) -> None:
        e = self._selected_entry()
        if e:
            from ui.pages.explorer import SingleExplorerTab
            SingleExplorerTab.open_with_system(e.path)

    def action_open_containing(self) -> None:
        e = self._selected_entry()
        if e:
            self.open_in_explorer_requested.emit(e.parent_dir)

    def action_copy_path(self) -> Optional[str]:
        e = self._selected_entry()
        if e:
            clip = QApplication.clipboard()
            if clip:
                clip.setText(e.path)
            self.status_lbl.setText(f"Copied path: {e.path}")
            return e.path
        return None

    def action_inspect_selected(self) -> None:
        e = self._selected_entry()
        if e:
            self.inspect_file_requested.emit(e.path)

    def action_delete_selected(self) -> bool:
        e = self._selected_entry()
        if not e:
            return False
        ok, msg = self.ops.delete_to_recycle_bin(e.path)
        self.status_lbl.setText(msg)
        if ok:
            remaining = [x for x in self.results_model.entries() if x.path != e.path]
            self.results_model.set_entries(remaining)
        return ok

    def save_current_search(self, name: Optional[str] = None) -> None:
        if not name:
            name, ok = QInputDialog.getText(self, "Save Search", "Preset name:")
            if not ok or not name:
                return
        self.engine.save_search(name, self.build_query())
        self._refresh_saved_searches()
        self.status_lbl.setText(f"Saved search preset '{name}'.")

    def _refresh_saved_searches(self) -> None:
        self.saved_combo.clear()
        self.saved_combo.addItem("Saved Searches...")
        for s in self.settings_mgr.settings.saved_searches:
            self.saved_combo.addItem(str(s.get("name", "Preset")))

    def _load_saved_search(self, idx: int) -> None:
        if idx <= 0:
            return
        saved_list = self.settings_mgr.settings.saved_searches
        if idx - 1 < len(saved_list):
            preset = saved_list[idx - 1]
            self.query_input.setText(str(preset.get("text", "")))
            self.category_combo.setCurrentText(str(preset.get("category", "All")))
            exts = preset.get("extensions") or []
            self.ext_input.setText(", ".join(str(x) for x in exts) if isinstance(exts, list) else str(exts))
            min_b = preset.get("min_size_bytes")
            self.min_size_spin.setValue(int(min_b) // (1024 * 1024) if min_b else 0)
            self.fuzzy_chk.setChecked(bool(preset.get("fuzzy_match", False)))
            self.mode_combo.setCurrentText(str(preset.get("search_mode", "Direct")))
