"""
Disk Analyzer Module — Interactive Treemap drill-down, Top 100 largest files,
Top 50 largest folders, file-type breakdown, empty folders, old files,
forgotten downloads, large archives/installers, and CSV/PDF report exports.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from config.settings import SettingsManager
from core.disk_analyzer import DiskAnalysisResult, DiskAnalyzer
from resources.icons.icon_provider import format_bytes
from ui.components.treemap import InteractiveTreemapWidget
from ui.qt_compat import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    Qt,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Signal,
)
from workers.analysis_worker import DiskAnalysisWorker


class DiskAnalyzerPage(QWidget):
    """Dedicated storage intelligence & interactive treemap module."""

    inspect_file_requested = Signal(str)

    def __init__(
        self,
        settings_mgr: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_mgr = settings_mgr
        self.analyzer = DiskAnalyzer(settings_mgr)
        self.current_result: Optional[DiskAnalysisResult] = None
        self.current_treemap_root: str = ""
        self.worker: Optional[DiskAnalysisWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header & Controls
        top_row = QHBoxLayout()
        title_lbl = QLabel("Disk Space Analyzer & Interactive Treemap")
        title_lbl.setObjectName("PageTitle")
        top_row.addWidget(title_lbl, 1)

        self.path_input = QLineEdit(self.settings_mgr.settings.default_drive)
        self.path_input.setMinimumWidth(240)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 10240)
        self.threshold_spin.setValue(10)
        self.threshold_spin.setSuffix(" MB threshold")

        self.scan_btn = QPushButton("Analyze Path")
        self.scan_btn.setObjectName("PrimaryButton")
        self.scan_btn.clicked.connect(lambda: self.run_analysis(synchronous=False))

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_analysis)

        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(lambda: self.export_report("csv"))

        self.export_pdf_btn = QPushButton("Export PDF")
        self.export_pdf_btn.clicked.connect(lambda: self.export_report("pdf"))

        for w in (
            self.path_input,
            self.threshold_spin,
            self.scan_btn,
            self.cancel_btn,
            self.export_csv_btn,
            self.export_pdf_btn,
        ):
            top_row.addWidget(w)
        layout.addLayout(top_row)

        # Treemap Navigation Bar
        tm_nav = QHBoxLayout()
        self.tm_up_btn = QPushButton("↑ Up Folder in Treemap")
        self.tm_up_btn.clicked.connect(self.treemap_navigate_up)
        self.tm_path_lbl = QLabel("Treemap Root: Not scanned yet")
        self.tm_path_lbl.setObjectName("PageSubtitle")
        tm_nav.addWidget(self.tm_up_btn)
        tm_nav.addWidget(self.tm_path_lbl, 1)
        layout.addLayout(tm_nav)

        # Splitter: Interactive Treemap on top, Detailed Analysis Tabs below
        splitter = QSplitter(Qt.Vertical)
        self.treemap = InteractiveTreemapWidget()
        self.treemap.folder_clicked.connect(self.drill_into_treemap_folder)
        splitter.addWidget(self.treemap)

        self.tabs = QTabWidget()
        self.top_files_tbl = self._make_table(["Filename", "Category", "Size", "Exact File Path"])
        self.top_files_tbl.itemDoubleClicked.connect(self._on_top_file_double_clicked)
        self.top_folders_tbl = self._make_table(["Folder Name", "Total Size", "Exact Folder Path"])
        self.types_tbl = self._make_table(["Extension / Category", "Total Storage", "Share"])
        self.cleanup_tbl = self._make_table(["Finding Type", "Size", "Exact Path"])

        self.tabs.addTab(self.top_files_tbl, "Top 100 Largest Files")
        self.tabs.addTab(self.top_folders_tbl, "Top 50 Largest Folders")
        self.tabs.addTab(self.types_tbl, "File-Type Distribution")
        self.tabs.addTab(self.cleanup_tbl, "Empty Folders, Old Files & Installers")
        splitter.addWidget(self.tabs)
        layout.addWidget(splitter, 1)

        self.status_lbl = QLabel("Select a drive or folder and click Analyze Path.")
        self.status_lbl.setObjectName("PageSubtitle")
        layout.addWidget(self.status_lbl)

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setStretchLastSection(True)
        return tbl

    def run_analysis(self, synchronous: bool = False) -> Optional[DiskAnalysisResult]:
        target = self.path_input.text().strip() or "."
        thresh_b = self.threshold_spin.value() * 1024 * 1024
        if synchronous:
            res = self.analyzer.analyze(target, large_threshold_bytes=thresh_b)
            self._apply_result(res)
            return res

        if self.worker and self.worker.isRunning():
            return None
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.status_lbl.setText(f"Analyzing {target}...")
        self.worker = DiskAnalysisWorker(target, thresh_b, self.settings_mgr, self)
        self.worker.progress.connect(
            lambda cnt, cur: self.status_lbl.setText(f"Scanned {cnt:,} entries — {cur[:75]}")
        )
        self.worker.completed.connect(self._apply_result)
        self.worker.start()
        return None

    def cancel_analysis(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def _apply_result(self, res: DiskAnalysisResult) -> None:
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.current_result = res
        self.drill_into_treemap_folder(res.root_path)

        # Populate Top 100 Largest Files
        self.top_files_tbl.setRowCount(len(res.top_files))
        for r, fe in enumerate(res.top_files):
            self.top_files_tbl.setItem(r, 0, QTableWidgetItem(fe.name))
            self.top_files_tbl.setItem(r, 1, QTableWidgetItem(fe.category))
            self.top_files_tbl.setItem(r, 2, QTableWidgetItem(format_bytes(fe.size)))
            self.top_files_tbl.setItem(r, 3, QTableWidgetItem(fe.path))

        # Populate Top 50 Largest Folders
        self.top_folders_tbl.setRowCount(len(res.top_folders))
        for r, fld in enumerate(res.top_folders):
            self.top_folders_tbl.setItem(r, 0, QTableWidgetItem(f"📁 {fld.name}"))
            self.top_folders_tbl.setItem(r, 1, QTableWidgetItem(format_bytes(fld.total_bytes)))
            self.top_folders_tbl.setItem(r, 2, QTableWidgetItem(fld.path))

        # Populate File-Type Statistics
        ext_sorted = sorted(res.extension_bytes.items(), key=lambda x: x[1], reverse=True)
        tot = max(1, res.total_bytes)
        self.types_tbl.setRowCount(len(ext_sorted))
        for r, (ext, b_val) in enumerate(ext_sorted):
            pct = (b_val / tot) * 100.0
            self.types_tbl.setItem(r, 0, QTableWidgetItem(ext))
            self.types_tbl.setItem(r, 1, QTableWidgetItem(format_bytes(b_val)))
            self.types_tbl.setItem(r, 2, QTableWidgetItem(f"{pct:.1f}%"))

        # Populate Cleanup Findings (Empty folders, Forgotten downloads, Old files, Large archives/installers)
        findings: list[tuple[str, str, str]] = []
        for ef in res.empty_folders[:50]:
            findings.append(("Empty Folder", "0 B", ef))
        for fd in res.forgotten_downloads[:50]:
            findings.append(("Forgotten Download", format_bytes(fd.size), fd.path))
        for la in res.large_archives[:50]:
            findings.append(("Large Archive", format_bytes(la.size), la.path))
        for li in res.large_installers[:50]:
            findings.append(("Large Installer", format_bytes(li.size), li.path))
        for of in res.old_files[:50]:
            findings.append(("Old File (>180d)", format_bytes(of.size), of.path))

        self.cleanup_tbl.setRowCount(len(findings))
        for r, (kind, sz_txt, f_path) in enumerate(findings):
            self.cleanup_tbl.setItem(r, 0, QTableWidgetItem(kind))
            self.cleanup_tbl.setItem(r, 1, QTableWidgetItem(sz_txt))
            self.cleanup_tbl.setItem(r, 2, QTableWidgetItem(f_path))

        self.status_lbl.setText(
            f"Analysis complete: {res.total_files:,} files, {res.total_folders:,} folders ({format_bytes(res.total_bytes)})"
        )

    def _on_top_file_double_clicked(self, item: QTableWidgetItem) -> None:
        row = self.top_files_tbl.currentRow()
        path_item = self.top_files_tbl.item(row, 3)
        if path_item:
            self.inspect_file_requested.emit(path_item.text())

    def drill_into_treemap_folder(self, folder_path: str) -> None:
        if not self.current_result:
            return
        norm = os.path.abspath(folder_path)
        self.current_treemap_root = norm
        subfolders = self.analyzer.get_immediate_subfolders(
            norm, self.current_result.folder_sizes
        )
        if not subfolders:
            # Show top folders if leaf directory has no subfolders
            subfolders = self.current_result.top_folders[:15]
        self.treemap.set_folders(norm, subfolders)
        self.tm_path_lbl.setText(f"Treemap Root: {norm} ({len(subfolders)} child blocks)")

    def treemap_navigate_up(self) -> None:
        if not self.current_result or not self.current_treemap_root:
            return
        parent = os.path.dirname(self.current_treemap_root)
        if parent and len(parent) >= len(self.current_result.root_path):
            self.drill_into_treemap_folder(parent)

    def export_report(self, fmt: str, output_path: Optional[str] = None) -> bool:
        if not self.current_result:
            self.status_lbl.setText("Run an analysis before exporting.")
            return False
        if not output_path:
            ext_filter = "CSV Files (*.csv)" if fmt == "csv" else "PDF Files (*.pdf)"
            default_name = f"nexus_disk_report.{fmt}"
            output_path, _ = QFileDialog.getSaveFileName(self, "Export Analysis Report", default_name, ext_filter)
            if not output_path:
                return False
        if fmt == "csv":
            ok = self.analyzer.export_to_csv(self.current_result, output_path)
        else:
            ok = self.analyzer.export_to_pdf(self.current_result, output_path)
        self.status_lbl.setText(
            f"Exported {fmt.upper()} report to {output_path}" if ok else "Export failed."
        )
        return ok
