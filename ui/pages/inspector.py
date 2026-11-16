"""
File Inspector Page — Deep File Properties, SHA-256 Digest, MIME Type,
and Safe Non-Executing Previews for PDF, Images, Excel (.xlsx), Word (.docx), and Source/Text.
"""

from __future__ import annotations

from typing import Optional

from core.file_inspector import FileInspectionReport, FileInspector
from resources.icons.icon_provider import format_bytes
from ui.qt_compat import (
    PYSIDE6_AVAILABLE,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPixmap,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FileInspectorPage(QWidget):
    """Non-executing file properties and multi-format document/image/code previewer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.inspector = FileInspector()
        self.current_report: Optional[FileInspectionReport] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("File Inspector & Safe Multi-Format Previewer")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Inspect cryptographic SHA-256 hashes, timestamps, MIME metadata, and preview PDFs, "
            "Images, Word (.docx), Excel (.xlsx), and Source Code without executing binaries."
        )
        sub.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(sub)

        top_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Paste or select a file path to inspect...")
        self.path_input.returnPressed.connect(lambda: self.inspect_file(self.path_input.text()))

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_file)

        self.inspect_btn = QPushButton("Inspect File")
        self.inspect_btn.setObjectName("PrimaryButton")
        self.inspect_btn.clicked.connect(lambda: self.inspect_file(self.path_input.text()))

        self.open_default_btn = QPushButton("Open in Default Windows App")
        self.open_default_btn.clicked.connect(self._open_default)

        top_row.addWidget(self.path_input, 1)
        top_row.addWidget(self.browse_btn)
        top_row.addWidget(self.inspect_btn)
        top_row.addWidget(self.open_default_btn)
        layout.addLayout(top_row)

        splitter = QSplitter(Qt.Horizontal)

        # Left Metadata Table
        self.meta_table = QTableWidget(0, 2)
        self.meta_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.meta_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.meta_table)

        # Right Preview Panel
        preview_card = QFrame()
        preview_card.setObjectName("SurfaceCard")
        pl = QVBoxLayout(preview_card)
        self.preview_header = QLabel("Document / Media / Code Preview")
        self.preview_header.setObjectName("SectionHeader")
        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setVisible(False)
        self.preview_box = QPlainTextEdit()
        self.preview_box.setReadOnly(True)
        pl.addWidget(self.preview_header)
        pl.addWidget(self.image_preview)
        pl.addWidget(self.preview_box, 1)
        splitter.addWidget(preview_card)

        layout.addWidget(splitter, 1)

    def inspect_file(self, file_path: str) -> Optional[FileInspectionReport]:
        clean = file_path.strip()
        if not clean:
            return None
        self.path_input.setText(clean)
        report = self.inspector.inspect(clean, compute_hash=True)
        self.current_report = report
        if not report:
            self.preview_box.setPlainText(f"File not found or inaccessible: {clean}")
            return None

        rows = [
            ("Filename", report.filename),
            ("Full Path", report.full_path),
            ("Extension", report.extension or "(none)"),
            ("Category", report.category),
            ("Exact Size", f"{format_bytes(report.size_bytes)} ({report.size_bytes:,} bytes)"),
            ("Created Date", report.created_at),
            ("Modified Date", report.modified_at),
            ("Last Accessed", report.accessed_at),
            ("SHA-256 Hash", report.sha256 or "Not computed (Folder or >250 MB)"),
            ("MIME Type", report.mime_type),
            ("Read-Only", "Yes" if report.is_readonly else "No"),
        ]
        if report.image_dimensions:
            rows.append(("Image Dimensions", f"{report.image_dimensions[0]} x {report.image_dimensions[1]} px"))
        for k, v in report.extra_metadata.items():
            rows.append((str(k), str(v)))

        self.meta_table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.meta_table.setItem(r, 0, QTableWidgetItem(k))
            self.meta_table.setItem(r, 1, QTableWidgetItem(v))

        self.preview_header.setText(f"Preview ({report.preview_type.upper()}) — {report.filename}")
        if report.preview_type == "image" and PYSIDE6_AVAILABLE:
            pix = QPixmap(report.full_path)
            if not pix.isNull():
                self.image_preview.setPixmap(
                    pix.scaled(520, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.image_preview.setVisible(True)
            else:
                self.image_preview.setVisible(False)
        else:
            self.image_preview.setVisible(False)
        self.preview_box.setPlainText(
            report.preview_text or "Metadata-only format. Click 'Open in Default Windows App' to launch."
        )
        return report

    def _browse_file(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Select File to Inspect")
        if chosen:
            self.inspect_file(chosen)

    def _open_default(self) -> None:
        if self.current_report:
            from ui.pages.explorer import SingleExplorerTab
            SingleExplorerTab.open_with_system(self.current_report.full_path)
