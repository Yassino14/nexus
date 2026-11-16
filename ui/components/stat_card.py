"""
Reusable metric card widget for NEXUS FILES.
"""

from __future__ import annotations

from ui.qt_compat import QFrame, QLabel, QVBoxLayout, QWidget


class StatCard(QFrame):
    """Dark surface KPI card displaying title, large value, and subtitle badge."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        subtitle: str = "",
        accent_hex: str = "#6366F1",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self.setMinimumWidth(165)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("StatLabel")

        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("StatValue")
        self.value_lbl.setStyleSheet(f"color: #F8FAFC; border-left: 3px solid {accent_hex}; padding-left: 8px;")

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("PageSubtitle")

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.sub_lbl)

    def update_metric(self, value: str, subtitle: str | None = None) -> None:
        self.value_lbl.setText(value)
        if subtitle is not None:
            self.sub_lbl.setText(subtitle)
