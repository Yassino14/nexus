"""
Advanced File Explorer Page.
Supports C:\\ and D:\\ navigation, Back/Forward history, interactive Breadcrumb bar,
Multiple Tabs, Dual-Pane side-by-side commander mode, Grid/List/Detailed views,
Keyboard shortcuts (Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+A, F2, Delete, Backspace, Ctrl+F, F5),
Recycle Bin safe deletion, Undo, and opening files with Windows default applications.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from config.settings import SettingsManager, classify_extension
from core.file_operations import FileOperationsManager
from core.file_scanner import ScannedEntry
from resources.icons.icon_provider import format_bytes, get_file_glyph
from ui.components.file_table import VirtualFileTableModel
from ui.qt_compat import (
    PYSIDE6_AVAILABLE,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDesktopServices,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QKeySequence,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QModelIndex,
    QPushButton,
    QShortcut,
    QSize,
    QSplitter,
    QStackedWidget,
    Qt,
    QTabWidget,
    QTableView,
    QUrl,
    QVBoxLayout,
    QWidget,
    Signal,
)


class SingleExplorerTab(QWidget):
    """A single navigable explorer tab with history, breadcrumb buttons, and virtualized views."""

    path_changed = Signal(str)
    inspect_requested = Signal(str)
    status_message = Signal(str)
    context_action_requested = Signal(str)

    def __init__(
        self,
        initial_path: str,
        ops: FileOperationsManager,
        settings_mgr: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ops = ops
        self.settings_mgr = settings_mgr
        self.current_path = os.path.abspath(initial_path if os.path.exists(initial_path) else ".")
        self.back_stack: List[str] = []
        self.forward_stack: List[str] = []
        self._all_entries: List[ScannedEntry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Navigation & Address Bar
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        self.back_btn = QPushButton("←")
        self.back_btn.setToolTip("Back (Backspace)")
        self.back_btn.clicked.connect(self.navigate_back)

        self.fwd_btn = QPushButton("→")
        self.fwd_btn.setToolTip("Forward")
        self.fwd_btn.clicked.connect(self.navigate_forward)

        self.up_btn = QPushButton("↑ Up")
        self.up_btn.clicked.connect(self.navigate_up)

        self.path_input = QLineEdit(self.current_path)
        self.path_input.returnPressed.connect(lambda: self.navigate_to(self.path_input.text()))

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Quick filter folder (Ctrl+F)...")
        self.filter_input.setMaximumWidth(210)
        self.filter_input.textChanged.connect(self._apply_filter)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.clicked.connect(self.refresh)

        nav_row.addWidget(self.back_btn)
        nav_row.addWidget(self.fwd_btn)
        nav_row.addWidget(self.up_btn)
        nav_row.addWidget(self.path_input, 1)
        nav_row.addWidget(self.filter_input)
        nav_row.addWidget(self.refresh_btn)
        layout.addLayout(nav_row)

        # Quick-Access Locations & Breadcrumb Bar Container
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        home_p = Path.home()
        quick_targets = [
            ("💾 C:\\", "C:\\"),
            ("💾 D:\\", "D:\\"),
            ("🖥️ Desktop", str(home_p / "Desktop")),
            ("⬇️ Downloads", str(home_p / "Downloads")),
            ("📄 Documents", str(home_p / "Documents")),
        ]
        for q_label, q_path in quick_targets:
            if os.path.exists(q_path):
                q_btn = QPushButton(q_label)
                q_btn.setStyleSheet("padding: 3px 9px; font-size: 11px;")
                q_btn.clicked.connect(lambda checked=False, p=q_path: self.navigate_to(p))
                quick_row.addWidget(q_btn)
        quick_row.addStretch()
        layout.addLayout(quick_row)

        self.breadcrumb_container = QWidget()
        self.breadcrumb_container_layout = QVBoxLayout(self.breadcrumb_container)
        self.breadcrumb_container_layout.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_bar = QWidget()
        self.breadcrumb_container_layout.addWidget(self.breadcrumb_bar)
        layout.addWidget(self.breadcrumb_container)

        # View Stack (0 = Detailed TableView, 1 = Compact List/Grid View)
        self.view_stack = QStackedWidget()
        self.table_model = VirtualFileTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setSortingEnabled(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        self.grid_list_widget = QListWidget()
        self.grid_list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grid_list_widget.itemDoubleClicked.connect(self._on_grid_item_double_clicked)
        self.grid_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid_list_widget.customContextMenuRequested.connect(
            lambda p: self._show_context_menu(p, self.grid_list_widget)
        )

        self.view_stack.addWidget(self.table_view)
        self.view_stack.addWidget(self.grid_list_widget)
        layout.addWidget(self.view_stack, 1)

        self.footer_lbl = QLabel("0 items")
        self.footer_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.footer_lbl)

        self.refresh()

    def navigate_to(self, target_path: str, record_history: bool = True) -> bool:
        norm = os.path.abspath(target_path.strip())
        if not os.path.exists(norm) or not os.path.isdir(norm):
            self.status_message.emit(f"Directory not accessible: {norm}")
            return False
        if record_history and norm != self.current_path:
            self.back_stack.append(self.current_path)
            self.forward_stack.clear()
        self.current_path = norm
        self.path_input.setText(self.current_path)
        self.refresh()
        self.path_changed.emit(self.current_path)
        return True

    def navigate_back(self) -> None:
        if self.back_stack:
            prev = self.back_stack.pop()
            self.forward_stack.append(self.current_path)
            self.navigate_to(prev, record_history=False)

    def navigate_forward(self) -> None:
        if self.forward_stack:
            nxt = self.forward_stack.pop()
            self.back_stack.append(self.current_path)
            self.navigate_to(nxt, record_history=False)

    def navigate_up(self) -> None:
        parent = os.path.dirname(self.current_path)
        if parent and parent != self.current_path:
            self.navigate_to(parent)

    def refresh(self) -> None:
        entries: List[ScannedEntry] = []
        show_hidden = self.settings_mgr.settings.show_hidden_files
        try:
            with os.scandir(self.current_path) as it:
                for e in it:
                    try:
                        stat = e.stat(follow_symlinks=False)
                        is_dir = e.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    is_hidden = e.name.startswith(".") or bool(
                        getattr(stat, "st_file_attributes", 0) & 0x2
                    )
                    if not show_hidden and is_hidden:
                        continue
                    ext = "" if is_dir else os.path.splitext(e.name)[1].lower()
                    entries.append(
                        ScannedEntry(
                            path=e.path,
                            name=e.name,
                            parent_dir=self.current_path,
                            extension=ext,
                            category="Folder" if is_dir else classify_extension(ext),
                            size=0 if is_dir else int(stat.st_size),
                            mtime=float(stat.st_mtime),
                            ctime=float(getattr(stat, "st_ctime", stat.st_mtime)),
                            atime=float(getattr(stat, "st_atime", stat.st_mtime)),
                            is_dir=is_dir,
                            is_hidden=is_hidden,
                        )
                    )
        except PermissionError:
            self.status_message.emit(f"Access denied: {self.current_path}")
        except OSError as err:
            self.status_message.emit(f"Error reading folder: {err}")

        entries.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        self._all_entries = entries
        self._rebuild_breadcrumbs()
        self._apply_filter(self.filter_input.text())

    def _rebuild_breadcrumbs(self) -> None:
        new_bar = QWidget()
        bl = QHBoxLayout(new_bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)

        parts = Path(self.current_path).parts
        accum_parts: List[tuple[str, str]] = []
        accum = ""
        for part in parts:
            accum = str(Path(accum) / part) if accum else part
            accum_parts.append((part, accum))
        # Show at most the root + last 5 segments so deep paths never force horizontal overflow
        if len(accum_parts) > 6:
            display_items = [accum_parts[0], ("...", accum_parts[-5][1])] + accum_parts[-5:]
        else:
            display_items = accum_parts
        for idx, (part, target_p) in enumerate(display_items):
            btn = QPushButton(part[:24])
            btn.setToolTip(target_p)
            btn.setStyleSheet("padding: 2px 6px; font-size: 11px;")
            btn.clicked.connect(lambda checked=False, p=target_p: self.navigate_to(p))
            bl.addWidget(btn)
            if idx < len(display_items) - 1:
                sep = QLabel("›")
                sep.setObjectName("PageSubtitle")
                bl.addWidget(sep)
        bl.addStretch()

        old_bar = self.breadcrumb_bar
        self.breadcrumb_container_layout.removeWidget(old_bar)
        old_bar.setVisible(False)
        old_bar.deleteLater()
        self.breadcrumb_bar = new_bar
        self.breadcrumb_container_layout.addWidget(new_bar)

    def _apply_filter(self, text: str) -> None:
        q = text.strip().lower()
        if not q:
            filtered = self._all_entries
        else:
            filtered = [e for e in self._all_entries if q in e.name.lower()]

        self.table_model.set_entries(filtered)
        self.grid_list_widget.clear()
        for e in filtered:
            glyph = get_file_glyph(e.extension, e.is_dir)
            sz_txt = "" if e.is_dir else f" ({format_bytes(e.size)})"
            item = QListWidgetItem(f"{glyph} {e.name}{sz_txt}")
            item.setData(Qt.UserRole, e)
            self.grid_list_widget.addItem(item)

        dirs_c = sum(1 for e in filtered if e.is_dir)
        files_c = sum(1 for e in filtered if not e.is_dir)
        tot_b = sum(e.size for e in filtered if not e.is_dir)
        self.footer_lbl.setText(
            f"{dirs_c} folders, {files_c} files ({format_bytes(tot_b)}) in {self.current_path}"
        )

    def selected_entries(self) -> List[ScannedEntry]:
        if self.view_stack.currentIndex() == 1:
            selected: List[ScannedEntry] = []
            for item in self.grid_list_widget.selectedItems():
                entry = item.data(Qt.UserRole)
                if entry:
                    selected.append(entry)
            return selected

        rows = self.table_view.selectionModel().selectedRows()
        selected = []
        for r in rows:
            entry = self.table_model.get_entry(r.row())
            if entry:
                selected.append(entry)
        return selected

    def select_all(self) -> None:
        if self.view_stack.currentIndex() == 1:
            self.grid_list_widget.selectAll()
        else:
            self.table_view.selectAll()

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        entry = self.table_model.get_entry(index.row())
        if not entry:
            return
        if entry.is_dir:
            self.navigate_to(entry.path)
        else:
            self.open_with_system(entry.path)

    def _on_grid_item_double_clicked(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.UserRole)
        if not entry:
            return
        if entry.is_dir:
            self.navigate_to(entry.path)
        else:
            self.open_with_system(entry.path)

    @staticmethod
    def open_with_system(path: str) -> bool:
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
                return True
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return True
        except Exception:
            return False

    def _show_context_menu(self, pos: object, source_widget: object = None) -> None:
        menu = QMenu(self)
        menu.addAction("Open", self._ctx_open)
        menu.addAction("Inspect Properties", self._ctx_inspect)
        menu.addSeparator()
        menu.addAction("Copy", lambda: self.context_action_requested.emit("copy"))
        menu.addAction("Cut", lambda: self.context_action_requested.emit("cut"))
        menu.addAction("Paste", lambda: self.context_action_requested.emit("paste"))
        menu.addSeparator()
        menu.addAction("Rename", lambda: self.context_action_requested.emit("rename"))
        menu.addAction("New Folder", lambda: self.context_action_requested.emit("new_folder"))
        menu.addAction("Move to Recycle Bin", lambda: self.context_action_requested.emit("delete"))

        target_w = source_widget or self.table_view
        vp = target_w.viewport() if hasattr(target_w, "viewport") else target_w
        global_pos = vp.mapToGlobal(pos) if hasattr(vp, "mapToGlobal") else pos
        menu.exec(global_pos)  # type: ignore

    def _ctx_open(self) -> None:
        sel = self.selected_entries()
        if sel:
            if sel[0].is_dir:
                self.navigate_to(sel[0].path)
            else:
                self.open_with_system(sel[0].path)

    def _ctx_inspect(self) -> None:
        sel = self.selected_entries()
        if sel:
            self.inspect_requested.emit(sel[0].path)


class FileExplorerPage(QWidget):
    """Multi-tab, dual-pane Windows File Explorer with full clipboard and safety integration."""

    inspect_file_requested = Signal(str)

    def __init__(
        self,
        ops: FileOperationsManager,
        settings_mgr: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ops = ops
        self.settings_mgr = settings_mgr
        self.clipboard_paths: List[str] = []
        self.clipboard_mode: str = ""  # 'copy' or 'cut'

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setSpacing(6)

        # Toolbar Row (compact labels so it fits comfortably on 1366x768 screens)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)

        self.new_tab_btn = QPushButton("+ Tab")
        self.new_tab_btn.setToolTip("Open New Tab")
        self.new_tab_btn.clicked.connect(lambda: self.add_explorer_tab())

        self.new_folder_btn = QPushButton("📁 +Folder")
        self.new_folder_btn.setToolTip("Create New Folder")
        self.new_folder_btn.clicked.connect(self.action_new_folder)

        self.new_file_btn = QPushButton("📄 +File")
        self.new_file_btn.setToolTip("Create New File")
        self.new_file_btn.clicked.connect(self.action_new_file)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy (Ctrl+C)")
        self.copy_btn.clicked.connect(self.action_copy)

        self.cut_btn = QPushButton("Cut")
        self.cut_btn.setToolTip("Cut (Ctrl+X)")
        self.cut_btn.clicked.connect(self.action_cut)

        self.paste_btn = QPushButton("Paste")
        self.paste_btn.setToolTip("Paste (Ctrl+V)")
        self.paste_btn.clicked.connect(self.action_paste)

        self.rename_btn = QPushButton("Rename")
        self.rename_btn.setToolTip("Rename (F2)")
        self.rename_btn.clicked.connect(self.action_rename)

        self.delete_btn = QPushButton("Recycle")
        self.delete_btn.setToolTip("Move to Recycle Bin (Delete)")
        self.delete_btn.setObjectName("DangerButton")
        self.delete_btn.clicked.connect(self.action_delete)

        self.undo_btn = QPushButton("↶ Undo")
        self.undo_btn.clicked.connect(self.action_undo)

        self.inspect_btn = QPushButton("ⓘ Inspect")
        self.inspect_btn.clicked.connect(self.action_inspect)

        self.view_combo = QComboBox()
        self.view_combo.addItems(["Detailed View", "List View", "Grid View"])
        self.view_combo.currentTextChanged.connect(self._on_view_mode_changed)

        self.dual_pane_chk = QCheckBox("Dual-Pane")
        self.dual_pane_chk.stateChanged.connect(self._toggle_dual_pane)

        self.hidden_chk = QCheckBox("Hidden")
        self.hidden_chk.setChecked(self.settings_mgr.settings.show_hidden_files)
        self.hidden_chk.stateChanged.connect(self._toggle_hidden_files)

        for w in (
            self.new_tab_btn,
            self.new_folder_btn,
            self.new_file_btn,
            self.copy_btn,
            self.cut_btn,
            self.paste_btn,
            self.rename_btn,
            self.delete_btn,
            self.undo_btn,
            self.inspect_btn,
        ):
            toolbar.addWidget(w)
        toolbar.addStretch()
        for w in (self.view_combo, self.dual_pane_chk, self.hidden_chk):
            toolbar.addWidget(w)
        root_layout.addLayout(toolbar)

        # Dual-Pane Splitter holding Primary TabWidget and Secondary TabWidget
        self.splitter = QSplitter(Qt.Horizontal)
        self.left_tabs = QTabWidget()
        self.left_tabs.setTabsClosable(True)
        self.left_tabs.tabCloseRequested.connect(self._close_left_tab)

        self.right_tabs = QTabWidget()
        self.right_tabs.setTabsClosable(True)
        self.right_tabs.tabCloseRequested.connect(self._close_right_tab)
        self.right_tabs.setVisible(False)

        self.splitter.addWidget(self.left_tabs)
        self.splitter.addWidget(self.right_tabs)
        root_layout.addWidget(self.splitter, 1)

        self.status_lbl = QLabel("Ready.")
        self.status_lbl.setObjectName("PageSubtitle")
        root_layout.addWidget(self.status_lbl)

        self._register_shortcuts()
        self.add_explorer_tab(self.settings_mgr.settings.default_drive)
        self.add_right_pane_tab(self.settings_mgr.settings.default_drive)

    def _register_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+A", lambda: self.active_tab().select_all() if self.active_tab() else None),
            ("Ctrl+C", self.action_copy),
            ("Ctrl+X", self.action_cut),
            ("Ctrl+V", self.action_paste),
            ("F2", self.action_rename),
            ("Delete", self.action_delete),
            ("Backspace", lambda: self.active_tab().navigate_back() if self.active_tab() else None),
            ("Ctrl+F", lambda: self.active_tab().filter_input.setFocus() if self.active_tab() else None),
            ("F5", lambda: self.active_tab().refresh() if self.active_tab() else None),
        ]
        self._shortcut_objs = []
        for key, fn in shortcuts:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(fn)
            self._shortcut_objs.append(sc)

    def _handle_context_action(self, action_name: str) -> None:
        dispatch = {
            "copy": self.action_copy,
            "cut": self.action_cut,
            "paste": self.action_paste,
            "rename": self.action_rename,
            "new_folder": self.action_new_folder,
            "delete": self.action_delete,
        }
        fn = dispatch.get(action_name)
        if fn:
            fn()

    def add_explorer_tab(self, path: Optional[str] = None) -> SingleExplorerTab:
        start_p = path or self.settings_mgr.settings.default_drive
        if not os.path.exists(start_p):
            start_p = str(Path.home())
        tab = SingleExplorerTab(start_p, self.ops, self.settings_mgr, self)
        label = os.path.basename(tab.current_path) or tab.current_path
        idx = self.left_tabs.addTab(tab, label)
        self.left_tabs.setCurrentIndex(idx)
        tab.path_changed.connect(
            lambda new_p, t=tab: self.left_tabs.setTabText(
                self.left_tabs.indexOf(t), os.path.basename(new_p) or new_p
            )
        )
        tab.inspect_requested.connect(self.inspect_file_requested.emit)
        tab.status_message.connect(self.status_lbl.setText)
        tab.context_action_requested.connect(self._handle_context_action)
        return tab

    def add_right_pane_tab(self, path: Optional[str] = None) -> SingleExplorerTab:
        start_p = path or str(Path.home())
        if not os.path.exists(start_p):
            start_p = "."
        tab = SingleExplorerTab(start_p, self.ops, self.settings_mgr, self)
        label = os.path.basename(tab.current_path) or tab.current_path
        idx = self.right_tabs.addTab(tab, label)
        self.right_tabs.setCurrentIndex(idx)
        tab.path_changed.connect(
            lambda new_p, t=tab: self.right_tabs.setTabText(
                self.right_tabs.indexOf(t), os.path.basename(new_p) or new_p
            )
        )
        tab.inspect_requested.connect(self.inspect_file_requested.emit)
        tab.status_message.connect(self.status_lbl.setText)
        tab.context_action_requested.connect(self._handle_context_action)
        return tab

    def _close_left_tab(self, index: int) -> None:
        if self.left_tabs.count() > 1:
            w = self.left_tabs.widget(index)
            self.left_tabs.removeTab(index)
            if w:
                w.deleteLater()

    def _close_right_tab(self, index: int) -> None:
        if self.right_tabs.count() > 1:
            w = self.right_tabs.widget(index)
            self.right_tabs.removeTab(index)
            if w:
                w.deleteLater()

    def active_tab(self) -> Optional[SingleExplorerTab]:
        w = self.left_tabs.currentWidget()
        return w if isinstance(w, SingleExplorerTab) else None

    def _toggle_dual_pane(self) -> None:
        self.right_tabs.setVisible(self.dual_pane_chk.isChecked())

    def _toggle_hidden_files(self) -> None:
        self.settings_mgr.settings.show_hidden_files = self.hidden_chk.isChecked()
        self.settings_mgr.save()
        if self.active_tab():
            self.active_tab().refresh()

    def _on_view_mode_changed(self, mode_text: str) -> None:
        tab = self.active_tab()
        if not tab:
            return
        if mode_text == "Detailed View":
            tab.view_stack.setCurrentIndex(0)
        else:
            tab.view_stack.setCurrentIndex(1)
            if PYSIDE6_AVAILABLE and hasattr(QListWidget, "IconMode"):
                if mode_text == "Grid View":
                    tab.grid_list_widget.setViewMode(QListWidget.IconMode)
                    tab.grid_list_widget.setGridSize(QSize(140, 72))
                    tab.grid_list_widget.setWordWrap(True)
                else:
                    tab.grid_list_widget.setViewMode(QListWidget.ListMode)
                    tab.grid_list_widget.setGridSize(QSize())
                    tab.grid_list_widget.setWordWrap(False)

    def action_new_folder(self, name: Optional[str] = None) -> bool:
        tab = self.active_tab()
        if not tab:
            return False
        if not name:
            name, ok = QInputDialog.getText(self, "Create Folder", "New folder name:")
            if not ok or not name:
                return False
        ok, msg = self.ops.create_folder(tab.current_path, name)
        self.status_lbl.setText(msg)
        tab.refresh()
        return ok

    def action_new_file(self, name: Optional[str] = None) -> bool:
        tab = self.active_tab()
        if not tab:
            return False
        if not name:
            name, ok = QInputDialog.getText(self, "Create File", "New filename:")
            if not ok or not name:
                return False
        ok, msg = self.ops.create_file(tab.current_path, name)
        self.status_lbl.setText(msg)
        tab.refresh()
        return ok

    def action_copy(self) -> None:
        tab = self.active_tab()
        if not tab:
            return
        sel = tab.selected_entries()
        self.clipboard_paths = [e.path for e in sel]
        self.clipboard_mode = "copy"
        self.status_lbl.setText(f"Copied {len(self.clipboard_paths)} item(s) to clipboard.")

    def action_cut(self) -> None:
        tab = self.active_tab()
        if not tab:
            return
        sel = tab.selected_entries()
        self.clipboard_paths = [e.path for e in sel]
        self.clipboard_mode = "cut"
        self.status_lbl.setText(f"Cut {len(self.clipboard_paths)} item(s) to clipboard.")

    def action_paste(self) -> int:
        tab = self.active_tab()
        if not tab or not self.clipboard_paths:
            return 0
        count = 0
        for src in list(self.clipboard_paths):
            if self.clipboard_mode == "cut":
                ok, _ = self.ops.move_item(src, tab.current_path)
            else:
                ok, _ = self.ops.copy_item(src, tab.current_path)
            if ok:
                count += 1
        if self.clipboard_mode == "cut":
            self.clipboard_paths.clear()
            self.clipboard_mode = ""
        tab.refresh()
        self.status_lbl.setText(f"Pasted {count} item(s) into {tab.current_path}")
        return count

    def action_rename(self, new_name: Optional[str] = None) -> bool:
        tab = self.active_tab()
        if not tab:
            return False
        sel = tab.selected_entries()
        if not sel:
            return False
        target = sel[0]
        if not new_name:
            new_name, ok = QInputDialog.getText(
                self, "Rename Item", f"Rename '{target.name}' to:", text=target.name
            )
            if not ok or not new_name:
                return False
        ok, msg = self.ops.rename_item(target.path, new_name)
        self.status_lbl.setText(msg)
        tab.refresh()
        return ok

    def action_delete(self) -> int:
        tab = self.active_tab()
        if not tab:
            return 0
        sel = tab.selected_entries()
        if not sel:
            return 0
        deleted = 0
        for e in sel:
            ok, msg = self.ops.delete_to_recycle_bin(e.path)
            if ok:
                deleted += 1
            else:
                self.status_lbl.setText(msg)
        tab.refresh()
        self.status_lbl.setText(f"Moved {deleted} item(s) to Recycle Bin.")
        return deleted

    def action_undo(self) -> bool:
        ok, msg = self.ops.undo_last_operation()
        self.status_lbl.setText(msg)
        if self.active_tab():
            self.active_tab().refresh()
        return ok

    def action_inspect(self) -> None:
        tab = self.active_tab()
        if not tab:
            return
        sel = tab.selected_entries()
        if sel:
            self.inspect_file_requested.emit(sel[0].path)
