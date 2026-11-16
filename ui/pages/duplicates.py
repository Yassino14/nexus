"""
Duplicate Finder Page — Multistage Size + SHA-256 Duplicate Detection.
Never assumes identical names mean identical content, and never automatically deletes files.
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import List, Optional

from config.settings import SettingsManager
from core.duplicate_engine import DuplicateEngine, DuplicateScanReport
from core.file_operations import FileOperationsManager
from resources.icons.icon_provider import format_bytes
from ui.qt_compat import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    Qt,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    Signal,
)
from workers.hash_worker import DuplicateHashWorker


class DuplicateFinderPage(QWidget):
    """Multistage SHA-256 duplicate finder with safe selection and Recycle Bin integration."""

    open_in_explorer_requested = Signal(str)

    def __init__(
        self,
        ops: FileOperationsManager,
        settings_mgr: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ops = ops
        self.settings_mgr = settings_mgr
        self.engine = DuplicateEngine(settings_mgr)
        self.current_report: Optional[DuplicateScanReport] = None
        self.worker: Optional[DuplicateHashWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("SHA-256 Duplicate File Finder")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Multistage verification: Size grouping → Unique size pruning → 64 KB pre-hash → Full SHA-256 verification."
        )
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        # Controls Row
        ctrl = QHBoxLayout()
        self.path_input = QLineEdit(self.settings_mgr.settings.default_drive)
        self.min_kb_spin = QSpinBox()
        self.min_kb_spin.setRange(0, 102400)
        self.min_kb_spin.setValue(1)
        self.min_kb_spin.setSuffix(" KB min")

        self.scan_btn = QPushButton("Scan for Duplicates")
        self.scan_btn.setObjectName("PrimaryButton")
        self.scan_btn.clicked.connect(lambda: self.run_scan(synchronous=False))

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_scan)

        self.select_but_one_btn = QPushButton("Select All But One Copy")
        self.select_but_one_btn.clicked.connect(self.select_all_but_one)

        self.delete_selected_btn = QPushButton("Move Selected to Recycle Bin")
        self.delete_selected_btn.setObjectName("DangerButton")
        self.delete_selected_btn.clicked.connect(self.delete_checked_duplicates)

        self.export_btn = QPushButton("Export Report (CSV)")
        self.export_btn.clicked.connect(lambda: self.export_report())

        for w in (
            self.path_input,
            self.min_kb_spin,
            self.scan_btn,
            self.cancel_btn,
            self.select_but_one_btn,
            self.delete_selected_btn,
            self.export_btn,
        ):
            ctrl.addWidget(w)
        layout.addLayout(ctrl)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "Duplicate Group / Filename",
            "Size",
            "Copies / Modified Date",
            "Potential Savings / Exact Location",
            "SHA-256 Digest",
        ])
        self.tree.header().setStretchLastSection(True)
        layout.addWidget(self.tree, 1)

        self.summary_lbl = QLabel("No duplicate scan run yet.")
        self.summary_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.summary_lbl)

    def run_scan(self, synchronous: bool = False) -> Optional[DuplicateScanReport]:
        root = self.path_input.text().strip() or "."
        min_b = max(1, self.min_kb_spin.value() * 1024)
        if synchronous:
            rep = self.engine.find_duplicates([root], min_size_bytes=min_b)
            self._apply_report(rep)
            return rep

        if self.worker and self.worker.isRunning():
            return None
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.worker = DuplicateHashWorker([root], min_b, self.settings_mgr, self)
        self.worker.progress.connect(
            lambda stg, cur, tot: self.summary_lbl.setText(f"{stg} ({cur:,} / {tot:,})")
        )
        self.worker.completed.connect(self._apply_report)
        self.worker.start()
        return None

    def cancel_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def _apply_report(self, report: DuplicateScanReport) -> None:
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.current_report = report
        self.tree.clear()

        for idx, grp in enumerate(report.groups, start=1):
            group_item = QTreeWidgetItem(
                self.tree,
                [
                    f"Group #{idx} ({grp.copies_count} identical copies)",
                    format_bytes(grp.file_size),
                    f"{grp.copies_count} copies",
                    f"Save {format_bytes(grp.recoverable_bytes)}",
                    grp.sha256[:24] + "...",
                ],
            )
            for fe in grp.files:
                dt = datetime.datetime.fromtimestamp(fe.mtime).strftime("%Y-%m-%d %H:%M")
                child = QTreeWidgetItem(
                    group_item,
                    [fe.name, format_bytes(fe.size), dt, fe.path, grp.sha256],
                )
                child.setCheckState(0, Qt.Unchecked)
                child.setData(0, Qt.UserRole, fe.path)

        self.tree.expandAll()
        self.summary_lbl.setText(
            f"Found {len(report.groups)} duplicate groups ({report.total_duplicate_files} redundant files) • "
            f"Recoverable storage: {format_bytes(report.total_recoverable_bytes)}"
        )

    def select_all_but_one(self) -> int:
        """Keep the first (oldest) copy in each group unchecked and check all redundant copies."""
        checked_count = 0
        for i in range(self.tree.topLevelItemCount()):
            grp_item = self.tree.topLevelItem(i)
            for j in range(grp_item.childCount()):
                child = grp_item.child(j)
                if j == 0:
                    child.setCheckState(0, Qt.Unchecked)
                else:
                    child.setCheckState(0, Qt.Checked)
                    checked_count += 1
        self.summary_lbl.setText(
            f"Selected {checked_count} duplicate copies for removal (preserving 1 original copy per group)."
        )
        return checked_count

    def get_checked_paths(self) -> List[str]:
        paths: List[str] = []
        for i in range(self.tree.topLevelItemCount()):
            grp_item = self.tree.topLevelItem(i)
            for j in range(grp_item.childCount()):
                child = grp_item.child(j)
                if child.checkState(0) == Qt.Checked:
                    p = child.data(0, Qt.UserRole)
                    if p:
                        paths.append(str(p))
        return paths

    def delete_checked_duplicates(self) -> int:
        targets = self.get_checked_paths()
        if not targets:
            self.summary_lbl.setText("No duplicate files selected.")
            return 0
        removed_paths: set[str] = set()
        for p in targets:
            ok, _ = self.ops.delete_to_recycle_bin(p)
            if ok:
                removed_paths.add(p)

        # Prune deleted children from the tree so the UI reflects disk state
        for i in range(self.tree.topLevelItemCount() - 1, -1, -1):
            grp_item = self.tree.topLevelItem(i)
            for j in range(grp_item.childCount() - 1, -1, -1):
                child = grp_item.child(j)
                if str(child.data(0, Qt.UserRole) or "") in removed_paths:
                    grp_item.removeChild(child)
            if grp_item.childCount() <= 1:
                self.tree.takeTopLevelItem(i)

        self.summary_lbl.setText(f"Moved {len(removed_paths)} selected duplicate files to Recycle Bin.")
        return len(removed_paths)

    def export_report(self, output_path: Optional[str] = None) -> bool:
        if not self.current_report:
            return False
        if not output_path:
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Export Duplicate Report", "nexus_duplicates.csv", "CSV Files (*.csv)"
            )
            if not output_path:
                return False
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Group", "SHA-256", "Size (Bytes)", "Filename", "Full Path"])
                for idx, grp in enumerate(self.current_report.groups, start=1):
                    for fe in grp.files:
                        w.writerow([idx, grp.sha256, grp.file_size, fe.name, fe.path])
            return True
        except Exception:
            return False
