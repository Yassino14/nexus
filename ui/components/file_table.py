"""
Virtualized QAbstractTableModel for displaying tens or hundreds of thousands
of files in File Explorer, Global Search, and Large File Finder without UI freezes.
"""

from __future__ import annotations

import datetime
from typing import Any, List

from core.file_scanner import ScannedEntry
from resources.icons.icon_provider import format_bytes, get_file_glyph
from ui.qt_compat import QAbstractTableModel, QModelIndex, Qt


class VirtualFileTableModel(QAbstractTableModel):
    """High-performance virtualized table model backed by a list of ScannedEntry objects."""

    COLUMNS = ["Name", "Size", "Type", "Extension", "Modified Date", "Full Location"]

    def __init__(self, entries: List[ScannedEntry] | None = None, parent: object = None) -> None:
        super().__init__(parent)
        self._entries: List[ScannedEntry] = entries or []

    def set_entries(self, entries: List[ScannedEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def get_entry(self, row: int) -> ScannedEntry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def entries(self) -> List[ScannedEntry]:
        return self._entries

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: int = Qt.Horizontal,
        role: int = Qt.DisplayRole,
    ) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if not (0 <= row < len(self._entries)):
            return None

        entry = self._entries[row]
        if role == Qt.DisplayRole:
            if col == 0:
                glyph = get_file_glyph(entry.extension, entry.is_dir)
                return f"{glyph}  {entry.name}"
            if col == 1:
                return "—" if entry.is_dir else format_bytes(entry.size)
            if col == 2:
                return entry.category
            if col == 3:
                return "Folder" if entry.is_dir else (entry.extension or "—")
            if col == 4:
                try:
                    return datetime.datetime.fromtimestamp(entry.mtime).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    return "—"
            if col == 5:
                return entry.parent_dir
        elif role == Qt.UserRole:
            return entry
        return None

    def sort(self, column: int, order: int = Qt.AscendingOrder) -> None:
        reverse = order == Qt.DescendingOrder
        self.beginResetModel()
        if column == 0:
            self._entries.sort(key=lambda e: (not e.is_dir, e.name.lower()), reverse=reverse)
        elif column == 1:
            self._entries.sort(key=lambda e: e.size, reverse=reverse)
        elif column == 2:
            self._entries.sort(key=lambda e: e.category.lower(), reverse=reverse)
        elif column == 3:
            self._entries.sort(key=lambda e: e.extension.lower(), reverse=reverse)
        elif column == 4:
            self._entries.sort(key=lambda e: e.mtime, reverse=reverse)
        elif column == 5:
            self._entries.sort(key=lambda e: e.parent_dir.lower(), reverse=reverse)
        self.endResetModel()
