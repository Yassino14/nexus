"""
Disk Analyzer & Storage Intelligence Module.
Computes folder size hierarchies for interactive Treemap drill-down,
Top 100 largest files, Top 50 largest folders, empty folders, old files,
forgotten downloads, large archives/installers, and exports CSV & PDF reports.
"""

from __future__ import annotations

import csv
import heapq
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config.settings import FILE_CATEGORIES, SettingsManager
from core.file_scanner import FileScanner, ScannedEntry

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


@dataclass
class FolderStat:
    """Aggregated storage metrics for a folder."""

    path: str
    name: str
    total_bytes: int = 0
    direct_bytes: int = 0
    files_count: int = 0
    children: Dict[str, "FolderStat"] = field(default_factory=dict)


@dataclass
class DiskAnalysisResult:
    """Comprehensive storage analysis output."""

    root_path: str
    total_bytes: int = 0
    total_files: int = 0
    total_folders: int = 0
    top_files: List[ScannedEntry] = field(default_factory=list)
    top_folders: List[FolderStat] = field(default_factory=list)
    folder_sizes: Dict[str, int] = field(default_factory=dict)
    extension_bytes: Dict[str, int] = field(default_factory=dict)
    category_bytes: Dict[str, int] = field(default_factory=dict)
    empty_folders: List[str] = field(default_factory=list)
    old_files: List[ScannedEntry] = field(default_factory=list)
    forgotten_downloads: List[ScannedEntry] = field(default_factory=list)
    large_archives: List[ScannedEntry] = field(default_factory=list)
    large_installers: List[ScannedEntry] = field(default_factory=list)
    inaccessible_paths: List[str] = field(default_factory=list)
    completed_at: float = field(default_factory=time.time)
    cancelled: bool = False


class DiskAnalyzer:
    """Performs deep disk analysis and exports CSV/PDF reports."""

    def __init__(self, settings_mgr: Optional[SettingsManager] = None) -> None:
        self.settings_mgr = settings_mgr or SettingsManager()
        self.scanner = FileScanner(self.settings_mgr)

    def analyze(
        self,
        root_path: str | Path,
        large_threshold_bytes: int = 10 * 1024 * 1024,
        old_days_threshold: int = 180,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> DiskAnalysisResult:
        """Scan `root_path` and build complete storage breakdown."""
        root_str = os.path.abspath(str(root_path))
        res = DiskAnalysisResult(root_path=root_str)
        now = time.time()
        old_cutoff = now - (old_days_threshold * 86400)
        forgotten_cutoff = now - (30 * 86400)

        top_files_heap: List[tuple[int, str, ScannedEntry]] = []
        folder_sizes: Dict[str, int] = {root_str: 0}
        folder_child_counts: Dict[str, int] = {}

        archive_exts = set(FILE_CATEGORIES["Archives"])
        installer_exts = set(FILE_CATEGORIES["Installers"])

        for idx, entry in enumerate(
            self.scanner.iter_directory(
                root_str,
                recursive=True,
                include_dirs=True,
                cancel_check=cancel_check,
                inaccessible_log=res.inaccessible_paths,
            ),
            start=1,
        ):
            if cancel_check and cancel_check():
                res.cancelled = True
                break

            folder_child_counts[entry.parent_dir] = folder_child_counts.get(entry.parent_dir, 0) + 1

            if entry.is_dir:
                res.total_folders += 1
                folder_sizes.setdefault(entry.path, 0)
                folder_child_counts.setdefault(entry.path, 0)
            else:
                res.total_files += 1
                res.total_bytes += entry.size
                ext = entry.extension or "(no ext)"
                res.extension_bytes[ext] = res.extension_bytes.get(ext, 0) + entry.size
                res.category_bytes[entry.category] = (
                    res.category_bytes.get(entry.category, 0) + entry.size
                )

                # Propagate file size up ancestor folders to root_str
                curr = entry.parent_dir
                while True:
                    folder_sizes[curr] = folder_sizes.get(curr, 0) + entry.size
                    if curr == root_str or len(curr) <= len(root_str):
                        break
                    parent = os.path.dirname(curr)
                    if parent == curr:
                        break
                    curr = parent

                # Maintain Top 100 largest files via min-heap
                if len(top_files_heap) < 100:
                    heapq.heappush(top_files_heap, (entry.size, entry.path, entry))
                elif entry.size > top_files_heap[0][0]:
                    heapq.heapreplace(top_files_heap, (entry.size, entry.path, entry))

                if entry.mtime < old_cutoff and len(res.old_files) < 200:
                    res.old_files.append(entry)

                if "download" in entry.parent_dir.lower() and entry.mtime < forgotten_cutoff:
                    if len(res.forgotten_downloads) < 200:
                        res.forgotten_downloads.append(entry)

                if entry.size >= large_threshold_bytes:
                    if entry.extension in archive_exts:
                        res.large_archives.append(entry)
                    elif entry.extension in installer_exts:
                        res.large_installers.append(entry)

            if progress_callback and idx % 400 == 0:
                progress_callback(idx, entry.parent_dir)

        res.top_files = [item[2] for item in sorted(top_files_heap, key=lambda x: x[0], reverse=True)]
        res.folder_sizes = folder_sizes

        # Top 50 largest folders
        sorted_folders = sorted(folder_sizes.items(), key=lambda x: x[1], reverse=True)[:50]
        res.top_folders = [
            FolderStat(
                path=f_path,
                name=os.path.basename(f_path) or f_path,
                total_bytes=f_bytes,
            )
            for f_path, f_bytes in sorted_folders
        ]

        res.empty_folders = [
            f_path
            for f_path, count in folder_child_counts.items()
            if count == 0 and f_path != root_str
        ][:500]

        res.large_archives.sort(key=lambda e: e.size, reverse=True)
        res.large_installers.sort(key=lambda e: e.size, reverse=True)
        res.completed_at = time.time()
        return res

    def get_immediate_subfolders(
        self, parent_folder: str, folder_sizes: Dict[str, int]
    ) -> List[FolderStat]:
        """Return immediate child folders and their aggregated sizes for Treemap drill-down."""
        norm_parent = os.path.abspath(parent_folder)
        children: List[FolderStat] = []
        for f_path, sz in folder_sizes.items():
            if f_path == norm_parent:
                continue
            if os.path.dirname(f_path) == norm_parent and sz > 0:
                children.append(
                    FolderStat(
                        path=f_path,
                        name=os.path.basename(f_path) or f_path,
                        total_bytes=sz,
                    )
                )
        children.sort(key=lambda c: c.total_bytes, reverse=True)
        return children

    @staticmethod
    def export_to_csv(result: DiskAnalysisResult, output_path: str | Path) -> bool:
        """Export disk analysis summary, top folders, and top files to CSV."""
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["NEXUS FILES - Disk Analysis Report"])
                writer.writerow(["Root Path", result.root_path])
                writer.writerow(["Total Files", result.total_files])
                writer.writerow(["Total Folders", result.total_folders])
                writer.writerow(["Total Bytes", result.total_bytes])
                writer.writerow([])
                writer.writerow(["--- TOP 50 LARGEST FOLDERS ---"])
                writer.writerow(["Folder Name", "Full Path", "Size (Bytes)"])
                for folder in result.top_folders:
                    writer.writerow([folder.name, folder.path, folder.total_bytes])
                writer.writerow([])
                writer.writerow(["--- TOP 100 LARGEST FILES ---"])
                writer.writerow(["Filename", "Extension", "Category", "Size (Bytes)", "Full Path"])
                for file_entry in result.top_files:
                    writer.writerow([
                        file_entry.name,
                        file_entry.extension,
                        file_entry.category,
                        file_entry.size,
                        file_entry.path,
                    ])
            return True
        except Exception:
            return False

    @staticmethod
    def export_to_pdf(result: DiskAnalysisResult, output_path: str | Path) -> bool:
        """Export disk analysis report to a clean PDF document."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if REPORTLAB_AVAILABLE:
            try:
                doc = SimpleDocTemplate(str(out), pagesize=A4)
                styles = getSampleStyleSheet()
                story = [
                    Paragraph("<b>NEXUS FILES — Disk Analysis Report</b>", styles["Title"]),
                    Spacer(1, 10),
                    Paragraph(f"<b>Analyzed Root:</b> {result.root_path}", styles["Normal"]),
                    Paragraph(
                        f"<b>Total Files:</b> {result.total_files:,} &nbsp;&nbsp; "
                        f"<b>Total Folders:</b> {result.total_folders:,} &nbsp;&nbsp; "
                        f"<b>Total Storage:</b> {result.total_bytes / (1024**2):.2f} MB",
                        styles["Normal"],
                    ),
                    Spacer(1, 14),
                    Paragraph("<b>Top Largest Folders</b>", styles["Heading2"]),
                ]
                folder_data = [["Folder", "Size (MB)", "Path"]]
                for fld in result.top_folders[:20]:
                    folder_data.append([
                        fld.name[:28],
                        f"{fld.total_bytes / (1024**2):.2f}",
                        fld.path[:55],
                    ])
                tbl = Table(folder_data, colWidths=[120, 80, 260])
                tbl.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ])
                )
                story.append(tbl)
                story.append(Spacer(1, 14))
                story.append(Paragraph("<b>Top Largest Files</b>", styles["Heading2"]))
                file_data = [["Filename", "Category", "Size (MB)", "Location"]]
                for fe in result.top_files[:25]:
                    file_data.append([
                        fe.name[:26],
                        fe.category,
                        f"{fe.size / (1024**2):.2f}",
                        fe.parent_dir[:45],
                    ])
                ftbl = Table(file_data, colWidths=[120, 70, 70, 200])
                ftbl.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ])
                )
                story.append(ftbl)
                doc.build(story)
                return True
            except Exception:
                pass

        # Minimal valid PDF fallback if reportlab is absent
        try:
            text_lines = [
                "NEXUS FILES - Disk Analysis Report",
                f"Root: {result.root_path}",
                f"Files: {result.total_files} | Folders: {result.total_folders} | Bytes: {result.total_bytes}",
            ]
            for fe in result.top_files[:15]:
                text_lines.append(f"{fe.name} ({fe.size} B) - {fe.path}")
            content = "\\n".join(text_lines).replace("(", "\\(").replace(")", "\\)")
            stream = f"BT /F1 10 Tf 40 760 Td ({content[:1200]}) Tj ET".encode("latin-1", errors="ignore")
            pdf_bytes = (
                b"%PDF-1.4\n"
                b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
                b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
                b"4 0 obj<</Length " + str(len(stream)).encode("ascii") + b">>stream\n" + stream + b"\nendstream\nendobj\n"
                b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
                b"xref\n0 6\n0000000000 65535 f \n"
                b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
            )
            out.write_bytes(pdf_bytes)
            return True
        except Exception:
            return False
