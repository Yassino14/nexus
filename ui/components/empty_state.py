"""
Carefully designed empty state component for tables, search results, and charts.
"""

from __future__ import annotations

from ui.qt_compat import QFrame, QLabel, Qt, QVBoxLayout, QWidget


class EmptyStateWidget(QFrame):
    """Polished empty state panel with icon, headline, and actionable hint."""

    def __init__(
        self,
        icon_text: str,
        headline: str,
        description: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 36, 32, 36)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon_text)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 32px; color: #6366F1;")

        title_lbl = QLabel(headline)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setObjectName("SectionHeader")

        desc_lbl = QLabel(description)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setObjectName("PageSubtitle")

        layout.addStretch()
        layout.addWidget(icon_lbl)
        layout.addWidget(title_lbl)
        layout.addWidget(desc_lbl)
        layout.addStretch()
