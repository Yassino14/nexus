"""
Folder Comparison Page — Non-Destructive Recursive Directory Comparator.
Identifies files in both folders, only in first, only in second, different sizes,
different SHA-256 hashes, and identical files, with CSV export.
"""

from __future__ import annotations

from typing import Optional

from core.folder_comparator import FolderComparator, FolderComparisonReport
from resources.icons.icon_provider import format_bytes
from ui.qt_compat import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FolderComparisonPage(QWidget):
    """Side-by-side recursive folder comparison utility."""

    def __init__(self, default_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.comparator = FolderComparator()
        self.current_report: Optional[FolderComparisonReport] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Folder Comparison Engine")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Compare two folder hierarchies recursively by relative path, byte size, and SHA-256 hash. "
            "Never modifies either folder."
        )
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        ctrl = QHBoxLayout()
        self.left_input = QLineEdit(default_dir)
        self.left_input.setPlaceholderText("First Folder (Left)...")
        self.right_input = QLineEdit(default_dir)
        self.right_input.setPlaceholderText("Second Folder (Right)...")

        self.hash_chk = QCheckBox("Verify SHA-256 Hashes")
        self.hash_chk.setChecked(True)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "All Items",
            "Existing in Both",
            "Only in First Folder",
            "Only in Second Folder",
            "Different Size",
            "Different SHA-256 Hash",
            "Identical Files",
        ])
        self.filter_combo.currentTextChanged.connect(lambda _: self._populate_table())

        self.compare_btn = QPushButton("Compare Folders")
        self.compare_btn.setObjectName("PrimaryButton")
        self.compare_btn.clicked.connect(self.run_comparison)

        self.export_btn = QPushButton("Export Comparison (CSV)")
        self.export_btn.clicked.connect(lambda: self.export_csv())

        for w in (
            QLabel("First:"),
            self.left_input,
            QLabel("Second:"),
            self.right_input,
            self.hash_chk,
            self.filter_combo,
            self.compare_btn,
            self.export_btn,
        ):
            ctrl.addWidget(w)
        layout.addLayout(ctrl)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Relative File Path",
            "Comparison Status",
            "First Folder Size",
            "Second Folder Size",
            "SHA-256 Verification",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.summary_lbl = QLabel("Select two folders above and click Compare Folders.")
        self.summary_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.summary_lbl)

    def run_comparison(self) -> FolderComparisonReport:
        rep = self.comparator.compare(
            self.left_input.text().strip(),
            self.right_input.text().strip(),
            verify_hashes=self.hash_chk.isChecked(),
        )
        self.current_report = rep
        self._populate_table()
        self.summary_lbl.setText(
            f"In Both: {rep.in_both_count} • Only First: {rep.only_left_count} • "
            f"Only Second: {rep.only_right_count} • Diff Size: {rep.different_size_count} • "
            f"Diff Hash: {rep.different_hash_count} • Identical: {rep.identical_count}"
        )
        return rep

    def _populate_table(self) -> None:
        if not self.current_report:
            return
        flt = self.filter_combo.currentText()
        items = self.current_report.items
        if flt == "Existing in Both":
            items = [i for i in items if i.status in ("identical", "different_size", "different_hash")]
        elif flt == "Only in First Folder":
            items = [i for i in items if i.status == "only_left"]
        elif flt == "Only in Second Folder":
            items = [i for i in items if i.status == "only_right"]
        elif flt == "Different Size":
            items = [i for i in items if i.status == "different_size"]
        elif flt == "Different SHA-256 Hash":
            items = [i for i in items if i.status == "different_hash"]
        elif flt == "Identical Files":
            items = [i for i in items if i.status == "identical"]

        self.table.setRowCount(len(items))
        for r, item in enumerate(items):
            l_sz = format_bytes(item.left_size) if item.left_size is not None else "—"
            r_sz = format_bytes(item.right_size) if item.right_size is not None else "—"
            hash_info = (
                "Match"
                if item.left_hash and item.left_hash == item.right_hash
                else ("Mismatch" if item.status == "different_hash" else "—")
            )
            self.table.setItem(r, 0, QTableWidgetItem(item.rel_path))
            self.table.setItem(r, 1, QTableWidgetItem(item.status))
            self.table.setItem(r, 2, QTableWidgetItem(l_sz))
            self.table.setItem(r, 3, QTableWidgetItem(r_sz))
            self.table.setItem(r, 4, QTableWidgetItem(hash_info))

    def export_csv(self, output_path: Optional[str] = None) -> bool:
        if not self.current_report:
            return False
        if not output_path:
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Export Comparison Report", "folder_comparison.csv", "CSV Files (*.csv)"
            )
            if not output_path:
                return False
        return self.comparator.export_to_csv(self.current_report, output_path)
