"""
Smart File Organizer Page — 100% Deterministic Rule-Based Organization (Zero AI).
Previews proposed moves into Documents/, Images/, Videos/, Audio/, Archives/,
Installers/, Programming/, University/, and Projects/, with batch confirmation and Undo.
"""

from __future__ import annotations

from typing import List, Optional

from core.file_operations import FileOperationsManager
from core.organizer import OrganizationProposal, SmartOrganizer
from resources.icons.icon_provider import format_bytes
from ui.qt_compat import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class SmartOrganizerPage(QWidget):
    """Rule-based file organization assistant with dry-run preview and one-click Undo."""

    def __init__(
        self,
        ops: FileOperationsManager,
        default_dir: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ops = ops
        self.organizer = SmartOrganizer(ops)
        self.proposals: List[OrganizationProposal] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Smart Rule-Based File Organizer")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Organize cluttered folders into structured categories (Documents, Images, Videos, Audio, Archives, "
            "Installers, Programming, University, Projects) using deterministic rules."
        )
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        ctrl = QHBoxLayout()
        self.src_input = QLineEdit(default_dir)
        self.src_input.setPlaceholderText("Source directory to organize...")
        self.dst_input = QLineEdit(default_dir)
        self.dst_input.setPlaceholderText("Destination base folder...")

        self.preview_btn = QPushButton("1. Preview Proposed Moves")
        self.preview_btn.setObjectName("PrimaryButton")
        self.preview_btn.clicked.connect(self.preview_organization)

        self.execute_btn = QPushButton("2. Execute Selected Moves")
        self.execute_btn.clicked.connect(self.execute_organization)

        self.undo_btn = QPushButton("↶ Undo Last Batch")
        self.undo_btn.clicked.connect(self.undo_last_batch)

        for w in (
            QLabel("Source:"),
            self.src_input,
            QLabel("Target Root:"),
            self.dst_input,
            self.preview_btn,
            self.execute_btn,
            self.undo_btn,
        ):
            ctrl.addWidget(w)
        layout.addLayout(ctrl)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Organize?",
            "Filename",
            "Size",
            "Matched Rule -> Target Category",
            "Proposed Destination Path (Editable)",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.status_lbl = QLabel("Click 'Preview Proposed Moves' to inspect suggested file locations.")
        self.status_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.status_lbl)

    def preview_organization(self) -> List[OrganizationProposal]:
        src = self.src_input.text().strip()
        dst = self.dst_input.text().strip() or src
        self.proposals = self.organizer.generate_proposals(src, dst)
        self.table.setRowCount(len(self.proposals))
        for r, prop in enumerate(self.proposals):
            chk = QTableWidgetItem(prop.target_folder_name)
            chk.setCheckState(Qt.Checked if prop.selected else Qt.Unchecked)
            self.table.setItem(r, 0, chk)
            self.table.setItem(r, 1, QTableWidgetItem(prop.filename))
            self.table.setItem(r, 2, QTableWidgetItem(format_bytes(prop.size_bytes)))
            self.table.setItem(r, 3, QTableWidgetItem(f"{prop.matched_rule} → {prop.target_folder_name}/"))
            self.table.setItem(r, 4, QTableWidgetItem(prop.proposed_destination))

        self.status_lbl.setText(
            f"Generated {len(self.proposals)} organization proposals (no files moved yet)."
        )
        return self.proposals

    def execute_organization(self) -> dict:
        for r, prop in enumerate(self.proposals):
            chk_item = self.table.item(r, 0)
            dest_item = self.table.item(r, 4)
            if chk_item:
                prop.selected = chk_item.checkState() == Qt.Checked
            if dest_item and dest_item.text().strip():
                prop.proposed_destination = dest_item.text().strip()

        res = self.organizer.execute_proposals(self.proposals)
        self.status_lbl.setText(
            f"Batch completed: {res['moved']} file(s) organized, {res['failed']} failed."
        )
        return res

    def undo_last_batch(self) -> int:
        restored, _ = self.organizer.undo_last_batch()
        self.status_lbl.setText(f"Undid batch organization: restored {restored} file(s).")
        return restored
