"""
Permanent 12-module left sidebar navigation inspired by Linear and Raycast.
"""

from __future__ import annotations

from typing import Dict, List

from resources.icons.icon_provider import NAV_ICONS
from ui.qt_compat import (
    QFrame,
    QLabel,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)


class SidebarNavigation(QFrame):
    """Permanent sidebar containing all 12 NEXUS FILES modules."""

    page_selected = Signal(int, str)

    PAGES: List[str] = [
        "Dashboard",
        "File Explorer",
        "Global Search",
        "Disk Analyzer",
        "Duplicate Finder",
        "Large Files",
        "Smart Organizer",
        "File Inspector",
        "Project Finder",
        "Recent Activity",
        "Folder Comparison",
        "Settings",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarFrame")
        self.setMinimumWidth(225)
        self.setMaximumWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 16)
        layout.setSpacing(4)

        brand_title = QLabel("NEXUS FILES")
        brand_title.setObjectName("BrandTitle")
        brand_sub = QLabel("LOCAL STORAGE INTELLIGENCE")
        brand_sub.setObjectName("BrandSubtitle")

        layout.addWidget(brand_title)
        layout.addWidget(brand_sub)
        layout.addSpacing(14)

        self.buttons: Dict[int, QPushButton] = {}
        for idx, name in enumerate(self.PAGES):
            glyph = NAV_ICONS.get(name, "•")
            btn = QPushButton(f"  {glyph}   {name}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, i=idx, n=name: self.select_page(i))
            layout.addWidget(btn)
            self.buttons[idx] = btn

        layout.addStretch()

        footer = QLabel("100% Offline • Zero Cloud • Safe Mode")
        footer.setObjectName("BrandSubtitle")
        layout.addWidget(footer)

        self.select_page(0)

    def select_page(self, index: int) -> None:
        for i, btn in self.buttons.items():
            btn.setChecked(i == index)
        if 0 <= index < len(self.PAGES):
            self.page_selected.emit(index, self.PAGES[index])
