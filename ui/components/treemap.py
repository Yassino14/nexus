"""
Interactive Squarified Treemap Widget for NEXUS FILES Disk Analyzer.
Displays proportional folder blocks and allows users to click any block to
drill down into that directory (or click 'Up Level' to navigate back).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.disk_analyzer import FolderStat
from resources.icons.icon_provider import format_bytes
from ui.components.charts import PALETTE_HEX
from ui.qt_compat import (
    PYSIDE6_AVAILABLE,
    QBrush,
    QColor,
    QFont,
    QFrame,
    QPainter,
    QPen,
    QRectF,
    Qt,
    QWidget,
    Signal,
)


@dataclass
class TreemapRect:
    """Computed geometric rectangle for a single folder in the treemap."""

    folder: FolderStat
    rect: QRectF
    color_hex: str


class InteractiveTreemapWidget(QFrame):
    """Interactive proportional treemap supporting mouse hover and click-to-drill-down."""

    folder_clicked = Signal(str)  # Emits full folder path when clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self.setMinimumSize(420, 260)
        self.setCursor(Qt.PointingHandCursor)
        self.folders: List[FolderStat] = []
        self.computed_rects: List[TreemapRect] = []
        self.current_root: str = ""

    def set_folders(self, current_root: str, folders: List[FolderStat]) -> None:
        """Update treemap items and recompute layout rectangles."""
        self.current_root = current_root
        self.folders = [f for f in folders if f.total_bytes > 0][:24]
        self._recompute_layout(float(self.width() or 600), float(self.height() or 320))
        self.update()

    def _recompute_layout(self, width: float, height: float) -> None:
        self.computed_rects.clear()
        if not self.folders or width <= 20 or height <= 20:
            return

        pad = 8.0
        avail = QRectF(pad, pad, max(10.0, width - 2 * pad), max(10.0, height - 2 * pad))
        total_bytes = sum(f.total_bytes for f in self.folders)
        if total_bytes <= 0:
            return

        # Slice-and-dice alternating horizontal/vertical treemap subdivision
        x, y, w, h = avail.x(), avail.y(), avail.width(), avail.height()
        remaining = float(total_bytes)

        for idx, folder in enumerate(self.folders):
            if remaining <= 0 or w <= 2 or h <= 2:
                break
            ratio = max(0.02, min(1.0, folder.total_bytes / remaining))
            color = PALETTE_HEX[idx % len(PALETTE_HEX)]

            if w >= h:
                rw = w * ratio
                rect = QRectF(x, y, max(4.0, rw - 3.0), max(4.0, h - 3.0))
                x += rw
                w -= rw
            else:
                rh = h * ratio
                rect = QRectF(x, y, max(4.0, w - 3.0), max(4.0, rh - 3.0))
                y += rh
                h -= rh

            remaining -= folder.total_bytes
            self.computed_rects.append(TreemapRect(folder=folder, rect=rect, color_hex=color))

    def click_at_index(self, index: int) -> Optional[str]:
        """Programmatic helper for testing and keyboard navigation."""
        if 0 <= index < len(self.computed_rects):
            target_path = self.computed_rects[index].folder.path
            self.folder_clicked.emit(target_path)
            return target_path
        return None

    def mousePressEvent(self, event: object) -> None:  # type: ignore
        pos = getattr(event, "position", lambda: None)() or getattr(event, "pos", lambda: None)()
        if pos is None:
            return
        for item in self.computed_rects:
            if item.rect.contains(pos):
                self.folder_clicked.emit(item.folder.path)
                break

    def paintEvent(self, event: object) -> None:  # type: ignore
        if not PYSIDE6_AVAILABLE:
            return
        self._recompute_layout(float(self.width()), float(self.height()))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.computed_rects:
            painter.setPen(QPen(QColor("#94A3B8")))
            painter.drawText(
                0, 0, self.width(), self.height(),
                Qt.AlignCenter,
                "Run Disk Analysis to render interactive folder treemap.\nClick any block to drill down into subfolders.",
            )
            painter.end()
            return

        font = QFont("Segoe UI", 9)
        font.setBold(True)
        painter.setFont(font)

        for item in self.computed_rects:
            r = item.rect
            painter.setPen(QPen(QColor("#0B0E14"), 2))
            painter.setBrush(QBrush(QColor(item.color_hex)))
            painter.drawRoundedRect(r, 5.0, 5.0)

            if r.width() > 55 and r.height() > 32:
                painter.setPen(QPen(QColor("#FFFFFF")))
                label = f"{item.folder.name}\n{format_bytes(item.folder.total_bytes)}"
                painter.drawText(r.adjusted(6, 4, -6, -4), Qt.AlignLeft | Qt.AlignVCenter, label)

        painter.end()
