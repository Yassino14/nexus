"""
Custom PyQtGraph & QPainter Data Visualization Widgets for NEXUS FILES:
- StorageDonutChart (used vs available or category share)
- HorizontalBarChartWidget (storage by extension, category, or age distribution)
Uses PyQtGraph when available and falls back to crisp custom QPainter rendering.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from resources.icons.icon_provider import format_bytes
from ui.qt_compat import (
    PYSIDE6_AVAILABLE,
    QBrush,
    QColor,
    QFont,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPen,
    QProgressBar,
    Qt,
    QVBoxLayout,
    QWidget,
)

try:
    import pyqtgraph as pg  # type: ignore
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pg = None
    PYQTGRAPH_AVAILABLE = False


PALETTE_HEX = [
    "#6366F1",  # Indigo
    "#06B6D4",  # Cyan
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#EC4899",  # Pink
    "#8B5CF6",  # Violet
    "#3B82F6",  # Blue
    "#14B8A6",  # Teal
]


class StorageDonutWidget(QFrame):
    """Donut chart widget visualizing storage capacity usage and breakdown."""

    def __init__(self, title: str = "Storage Usage", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self.setMinimumSize(180, 155)
        self.title = title
        self.segments: List[Tuple[str, float, str]] = [
            ("Used", 0.0, "#6366F1"),
            ("Available", 100.0, "#1E293B"),
        ]
        self.center_headline = "0%"
        self.center_subline = "0 GB / 0 GB"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.header_lbl = QLabel(title)
        self.header_lbl.setObjectName("SectionHeader")
        layout.addWidget(self.header_lbl)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setObjectName("PageSubtitle")
        layout.addStretch()
        layout.addWidget(self.summary_lbl)

    def set_usage(self, used_bytes: int, total_bytes: int, label_prefix: str = "") -> None:
        free_bytes = max(0, total_bytes - used_bytes)
        pct = round((used_bytes / total_bytes) * 100.0, 1) if total_bytes > 0 else 0.0
        color = "#EF4444" if pct >= 90 else "#F59E0B" if pct >= 75 else "#6366F1"
        self.segments = [
            ("Used", float(used_bytes), color),
            ("Free", float(free_bytes), "#1E293B"),
        ]
        self.center_headline = f"{pct:.1f}%"
        self.center_subline = f"{format_bytes(used_bytes)} / {format_bytes(total_bytes)}"
        self.summary_lbl.setText(
            f"{label_prefix}Used: {format_bytes(used_bytes)} ({pct:.1f}%) • Free: {format_bytes(free_bytes)}"
        )
        self.update()

    def paintEvent(self, event: object) -> None:  # type: ignore
        if not PYSIDE6_AVAILABLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        diameter = min(w - 40, h - 70)
        if diameter < 60:
            painter.end()
            return

        x = (w - diameter) // 2
        y = 36
        total_val = sum(max(0.0, s[1]) for s in self.segments) or 1.0

        start_angle = 90 * 16
        for _, val, hex_col in self.segments:
            span = int(-((val / total_val) * 360.0) * 16)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(hex_col)))
            painter.drawPie(x, y, diameter, diameter, start_angle, span)
            start_angle += span

        # Inner cutout for donut ring
        inner_d = int(diameter * 0.64)
        inner_x = x + (diameter - inner_d) // 2
        inner_y = y + (diameter - inner_d) // 2
        painter.setBrush(QBrush(QColor("#131924")))
        painter.drawEllipse(inner_x, inner_y, inner_d, inner_d)

        # Center percentage text
        painter.setPen(QPen(QColor("#F8FAFC")))
        f_big = QFont("Segoe UI", 14)
        f_big.setBold(True)
        painter.setFont(f_big)
        painter.drawText(inner_x, inner_y, inner_d, inner_d, Qt.AlignCenter, self.center_headline)
        painter.end()


class CategoryBreakdownChart(QFrame):
    """Clean horizontal bar distribution widget for extensions, categories, and file age."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(14, 12, 14, 12)
        self.layout_root.setSpacing(6)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("SectionHeader")
        self.layout_root.addWidget(self.title_lbl)

        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 4, 0, 0)
        self.rows_layout.setSpacing(6)
        self.layout_root.addWidget(self.rows_container)
        self.items_data: List[Tuple[str, int, str]] = []

    def set_data(
        self,
        data: Dict[str, int],
        is_bytes: bool = True,
        max_rows: int = 7,
    ) -> None:
        # Clear container by replacing widget
        new_container = QWidget()
        new_layout = QVBoxLayout(new_container)
        new_layout.setContentsMargins(0, 4, 0, 0)
        new_layout.setSpacing(6)

        sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)[:max_rows]
        total = sum(v for _, v in sorted_items) or 1
        self.items_data.clear()

        if not sorted_items:
            empty = QLabel("No scanned data yet. Run a scan to populate distribution.")
            empty.setObjectName("PageSubtitle")
            new_layout.addWidget(empty)
        else:
            for idx, (label, val) in enumerate(sorted_items):
                pct = int(round((val / total) * 100))
                val_str = format_bytes(val) if is_bytes else f"{val:,} files"
                color = PALETTE_HEX[idx % len(PALETTE_HEX)]
                self.items_data.append((label, val, val_str))

                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(0, 0, 0, 0)
                row_l.setSpacing(8)

                name_lbl = QLabel(str(label)[:18])
                name_lbl.setMinimumWidth(95)

                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(pct)
                bar.setFormat(f"{pct}%")
                bar.setStyleSheet(
                    f"QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}"
                )

                stat_lbl = QLabel(val_str)
                stat_lbl.setMinimumWidth(85)
                stat_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                stat_lbl.setObjectName("PageSubtitle")

                row_l.addWidget(name_lbl)
                row_l.addWidget(bar, 1)
                row_l.addWidget(stat_lbl)
                new_layout.addWidget(row_w)

        old_container = self.rows_container
        self.layout_root.removeWidget(old_container)
        old_container.setVisible(False)
        old_container.deleteLater()
        self.rows_container = new_container
        self.rows_layout = new_layout
        self.layout_root.addWidget(self.rows_container)
