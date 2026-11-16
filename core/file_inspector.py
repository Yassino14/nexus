"""
Non-Executing File Inspector & Multi-Format Preview Engine.
Extracts full metadata, SHA-256 hash, MIME type, image dimensions, and generates safe previews for:
- PDF (via PyMuPDF / fitz or pypdf fallback)
- Images (via Pillow)
- Excel .xlsx (via openpyxl)
- Word .docx (via python-docx)
- Text & Source Code (UTF-8 / Latin-1 safe read)
Never executes files to inspect them.
"""

from __future__ import annotations

import datetime
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import classify_extension
from core.duplicate_engine import DuplicateEngine

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None
    ExifTags = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import docx
except ImportError:
    docx = None


@dataclass
class FileInspectionReport:
    """Rich metadata and safe content preview for a single file."""

    filename: str
    full_path: str
    parent_dir: str
    extension: str
    category: str
    size_bytes: int
    created_at: str
    modified_at: str
    accessed_at: str
    sha256: Optional[str]
    mime_type: str
    is_readonly: bool
    image_dimensions: Optional[Tuple[int, int]] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)
    preview_type: str = "metadata_only"  # 'text', 'image', 'pdf', 'excel', 'word', 'metadata_only'
    preview_text: str = ""
    preview_table: List[List[str]] = field(default_factory=list)


class FileInspector:
    """Safely inspects file properties and generates previews without executing files."""

    TEXT_EXTENSIONS = {
        ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs",
        ".cpp", ".c", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".html",
        ".css", ".scss", ".sql", ".json", ".yaml", ".yml", ".xml", ".toml",
        ".ini", ".sh", ".bat", ".cmd", ".ps1", ".log", ".csv", ".gitignore",
    }

    def inspect(self, file_path: str | Path, compute_hash: bool = True) -> Optional[FileInspectionReport]:
        """Inspect `file_path` and populate metadata and preview."""
        p = Path(os.path.abspath(str(file_path)))
        if not p.exists():
            return None

        try:
            stat = p.stat()
        except OSError:
            return None

        ext = p.suffix.lower()
        cat = "Folder" if p.is_dir() else classify_extension(ext)
        mime_type, _ = mimetypes.guess_type(str(p))
        if not mime_type:
            mime_type = "inode/directory" if p.is_dir() else "application/octet-stream"

        sha = None
        if compute_hash and p.is_file() and stat.st_size <= 250 * 1024 * 1024:
            sha = DuplicateEngine.compute_sha256(p)

        report = FileInspectionReport(
            filename=p.name,
            full_path=str(p),
            parent_dir=str(p.parent),
            extension=ext,
            category=cat,
            size_bytes=0 if p.is_dir() else int(stat.st_size),
            created_at=self._fmt_ts(getattr(stat, "st_ctime", stat.st_mtime)),
            modified_at=self._fmt_ts(stat.st_mtime),
            accessed_at=self._fmt_ts(getattr(stat, "st_atime", stat.st_mtime)),
            sha256=sha,
            mime_type=mime_type,
            is_readonly=not os.access(p, os.W_OK),
        )

        if p.is_dir():
            return report

        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tif", ".tiff"):
            self._populate_image_preview(p, report)
        elif ext == ".pdf":
            self._populate_pdf_preview(p, report)
        elif ext in (".xlsx", ".xlsm"):
            self._populate_excel_preview(p, report)
        elif ext == ".docx":
            self._populate_word_preview(p, report)
        elif ext in self.TEXT_EXTENSIONS or (mime_type and mime_type.startswith("text/")):
            self._populate_text_preview(p, report)

        return report

    @staticmethod
    def _fmt_ts(ts: float) -> str:
        try:
            return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "Unknown"

    def _populate_image_preview(self, p: Path, report: FileInspectionReport) -> None:
        report.preview_type = "image"
        if Image is None:
            return
        try:
            with Image.open(p) as img:
                report.image_dimensions = img.size
                report.extra_metadata["Format"] = img.format or "Unknown"
                report.extra_metadata["Color Mode"] = img.mode
                report.preview_text = (
                    f"Image Format: {img.format} | Dimensions: {img.size[0]} x {img.size[1]} px | Mode: {img.mode}"
                )
        except Exception as e:
            report.preview_text = f"Unable to decode image metadata: {e}"

    def _populate_pdf_preview(self, p: Path, report: FileInspectionReport) -> None:
        report.preview_type = "pdf"
        if fitz is not None:
            try:
                doc = fitz.open(str(p))
                report.extra_metadata["Pages"] = len(doc)
                meta = doc.metadata or {}
                for k in ("title", "author", "creator", "producer"):
                    if meta.get(k):
                        report.extra_metadata[k.capitalize()] = meta[k]
                pages_text = []
                for idx in range(min(5, len(doc))):
                    pages_text.append(f"--- Page {idx + 1} ---\n" + doc[idx].get_text("text"))
                report.preview_text = "\n\n".join(pages_text).strip() or "(PDF contains no extractable text)"
                doc.close()
                return
            except Exception:
                pass

        if pypdf is not None:
            try:
                reader = pypdf.PdfReader(str(p))
                report.extra_metadata["Pages"] = len(reader.pages)
                pages_text = []
                for idx, page in enumerate(reader.pages[:5]):
                    pages_text.append(f"--- Page {idx + 1} ---\n" + (page.extract_text() or ""))
                report.preview_text = "\n\n".join(pages_text).strip() or "(PDF contains no extractable text)"
                return
            except Exception as e:
                report.preview_text = f"PDF preview unavailable: {e}"

    def _populate_excel_preview(self, p: Path, report: FileInspectionReport) -> None:
        report.preview_type = "excel"
        if openpyxl is None:
            report.preview_text = "openpyxl is required for Excel previews."
            return
        try:
            wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
            report.extra_metadata["Sheets"] = ", ".join(wb.sheetnames)
            sheet = wb.active
            rows_out: List[List[str]] = []
            lines_out: List[str] = [f"Active Sheet: {sheet.title} (Sheets: {', '.join(wb.sheetnames)})", ""]
            for row_idx, row in enumerate(sheet.iter_rows(values_only=True)):
                if row_idx >= 35:
                    break
                str_row = [str(cell) if cell is not None else "" for cell in row[:12]]
                rows_out.append(str_row)
                lines_out.append(" | ".join(str_row))
            report.preview_table = rows_out
            report.preview_text = "\n".join(lines_out)
            wb.close()
        except Exception as e:
            report.preview_text = f"Unable to preview Excel workbook: {e}"

    def _populate_word_preview(self, p: Path, report: FileInspectionReport) -> None:
        report.preview_type = "word"
        if docx is None:
            report.preview_text = "python-docx is required for Word previews."
            return
        try:
            document = docx.Document(str(p))
            paras = [para.text for para in document.paragraphs if para.text.strip()]
            report.extra_metadata["Paragraphs"] = len(paras)
            report.extra_metadata["Tables"] = len(document.tables)
            report.preview_text = "\n\n".join(paras[:60]) or "(Empty Word document)"
        except Exception as e:
            report.preview_text = f"Unable to preview Word document: {e}"

    def _populate_text_preview(self, p: Path, report: FileInspectionReport) -> None:
        report.preview_type = "text"
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                snippet = f.read(32768)
            report.preview_text = snippet
            report.extra_metadata["Lines (Sample)"] = snippet.count("\n") + 1
        except Exception as e:
            report.preview_text = f"Unable to read text file: {e}"
