"""
Non-Destructive Recursive Folder Comparison Engine.
Compares two directories by relative path, file size, and optional SHA-256 hash.
Categorizes items into:
- Only in Left (First folder)
- Only in Right (Second folder)
- Different Size
- Different Hash (same size, modified content)
- Identical Files
Supports exporting comparison reports to CSV.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.duplicate_engine import DuplicateEngine


@dataclass
class ComparedItem:
    """Comparison status for a relative path across two folders."""

    rel_path: str
    status: str  # 'identical', 'only_left', 'only_right', 'different_size', 'different_hash'
    left_size: Optional[int] = None
    right_size: Optional[int] = None
    left_mtime: Optional[float] = None
    right_mtime: Optional[float] = None
    left_hash: Optional[str] = None
    right_hash: Optional[str] = None


@dataclass
class FolderComparisonReport:
    """Complete recursive comparison summary between two folders."""

    left_root: str
    right_root: str
    items: List[ComparedItem] = field(default_factory=list)
    only_left_count: int = 0
    only_right_count: int = 0
    identical_count: int = 0
    different_size_count: int = 0
    different_hash_count: int = 0
    in_both_count: int = 0


class FolderComparator:
    """Compares two directories recursively without modifying either directory."""

    def compare(
        self,
        left_dir: str | Path,
        right_dir: str | Path,
        verify_hashes: bool = True,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> FolderComparisonReport:
        left_root = os.path.abspath(str(left_dir))
        right_root = os.path.abspath(str(right_dir))
        report = FolderComparisonReport(left_root=left_root, right_root=right_root)

        left_files = self._collect_relative_files(left_root, cancel_check)
        right_files = self._collect_relative_files(right_root, cancel_check)

        all_rels = sorted(set(left_files.keys()) | set(right_files.keys()))
        for rel in all_rels:
            if cancel_check and cancel_check():
                break
            l_meta = left_files.get(rel)
            r_meta = right_files.get(rel)

            if l_meta and not r_meta:
                report.only_left_count += 1
                report.items.append(
                    ComparedItem(
                        rel_path=rel,
                        status="only_left",
                        left_size=l_meta["size"],
                        left_mtime=l_meta["mtime"],
                    )
                )
            elif r_meta and not l_meta:
                report.only_right_count += 1
                report.items.append(
                    ComparedItem(
                        rel_path=rel,
                        status="only_right",
                        right_size=r_meta["size"],
                        right_mtime=r_meta["mtime"],
                    )
                )
            elif l_meta and r_meta:
                report.in_both_count += 1
                if l_meta["size"] != r_meta["size"]:
                    report.different_size_count += 1
                    report.items.append(
                        ComparedItem(
                            rel_path=rel,
                            status="different_size",
                            left_size=l_meta["size"],
                            right_size=r_meta["size"],
                            left_mtime=l_meta["mtime"],
                            right_mtime=r_meta["mtime"],
                        )
                    )
                else:
                    l_hash = None
                    r_hash = None
                    if verify_hashes:
                        l_hash = DuplicateEngine.compute_sha256(l_meta["full_path"], cancel_check)
                        r_hash = DuplicateEngine.compute_sha256(r_meta["full_path"], cancel_check)
                    if verify_hashes and l_hash != r_hash:
                        report.different_hash_count += 1
                        status = "different_hash"
                    else:
                        report.identical_count += 1
                        status = "identical"
                    report.items.append(
                        ComparedItem(
                            rel_path=rel,
                            status=status,
                            left_size=l_meta["size"],
                            right_size=r_meta["size"],
                            left_mtime=l_meta["mtime"],
                            right_mtime=r_meta["mtime"],
                            left_hash=l_hash,
                            right_hash=r_hash,
                        )
                    )
        return report

    @staticmethod
    def _collect_relative_files(
        root_dir: str, cancel_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Dict[str, object]]:
        mapping: Dict[str, Dict[str, object]] = {}
        if not os.path.exists(root_dir):
            return mapping
        for dirpath, _, filenames in os.walk(root_dir):
            if cancel_check and cancel_check():
                break
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root_dir).replace("\\", "/")
                try:
                    st = os.stat(full)
                    mapping[rel] = {
                        "full_path": full,
                        "size": int(st.st_size),
                        "mtime": float(st.st_mtime),
                    }
                except OSError:
                    continue
        return mapping

    @staticmethod
    def export_to_csv(report: FolderComparisonReport, output_path: str | Path) -> bool:
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["NEXUS FILES - Folder Comparison Report"])
                writer.writerow(["First Folder (Left)", report.left_root])
                writer.writerow(["Second Folder (Right)", report.right_root])
                writer.writerow([
                    "Summary",
                    f"Both: {report.in_both_count}",
                    f"Only First: {report.only_left_count}",
                    f"Only Second: {report.only_right_count}",
                    f"Diff Size: {report.different_size_count}",
                    f"Diff Hash: {report.different_hash_count}",
                    f"Identical: {report.identical_count}",
                ])
                writer.writerow([])
                writer.writerow(["Relative Path", "Status", "First Size (B)", "Second Size (B)", "First SHA-256", "Second SHA-256"])
                for item in report.items:
                    writer.writerow([
                        item.rel_path,
                        item.status,
                        item.left_size if item.left_size is not None else "",
                        item.right_size if item.right_size is not None else "",
                        item.left_hash or "",
                        item.right_hash or "",
                    ])
            return True
        except Exception:
            return False
