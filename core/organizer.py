"""
Smart Rule-Based File Organizer (100% Deterministic, Zero AI).
Classifies loose files into structured destination folders based on extension,
file type, naming patterns (e.g. university/coursework keywords, project artifacts),
and date, with full preview, customizable destinations, batch execution, and Undo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import classify_extension
from core.file_operations import FileOperationsManager
from core.file_scanner import FileScanner


@dataclass
class OrganizationProposal:
    """Proposed rule-based move for a single file."""

    source_path: str
    filename: str
    size_bytes: int
    matched_rule: str
    target_folder_name: str
    proposed_destination: str
    selected: bool = True


class SmartOrganizer:
    """Rule-based file organization engine."""

    UNIVERSITY_KEYWORDS = (
        "lecture", "syllabus", "assignment", "homework", "exam", "midterm",
        "thesis", "dissertation", "course", "lab_", "tp_", "td_", "tek-up", "university",
    )
    PROJECT_KEYWORDS = (
        "architecture", "spec", "wireframe", "backlog", "sprint", "schema", "uml", "release",
    )

    STANDARD_FOLDERS = [
        "Documents",
        "Images",
        "Videos",
        "Audio",
        "Archives",
        "Installers",
        "Programming",
        "University",
        "Projects",
    ]

    def __init__(self, ops_manager: Optional[FileOperationsManager] = None) -> None:
        self.ops = ops_manager or FileOperationsManager()
        self.scanner = FileScanner(self.ops.settings_mgr)
        self._last_batch_moves: List[Tuple[str, str]] = []

    def generate_proposals(
        self,
        source_dir: str | Path,
        destination_root: Optional[str | Path] = None,
    ) -> List[OrganizationProposal]:
        """
        Inspect top-level files in `source_dir` and propose deterministic
        rule-based destinations without modifying any files on disk.
        """
        src_root = Path(os.path.abspath(str(source_dir)))
        dst_root = Path(os.path.abspath(str(destination_root))) if destination_root else src_root
        if not src_root.exists():
            return []

        proposals: List[OrganizationProposal] = []
        try:
            with os.scandir(src_root) as it:
                for entry in it:
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        low_name = entry.name.lower()
                        if low_name.startswith(".") or low_name in ("desktop.ini", "thumbs.db", "ntuser.dat", "ntuser.ini"):
                            continue
                        if low_name.endswith((".lnk", ".url")):
                            continue
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue

                    folder_Bucket, rule_desc = self._classify_file(entry.name)
                    target_dir = dst_root / folder_Bucket
                    proposed_dest = target_dir / entry.name

                    if os.path.normcase(str(proposed_dest)) == os.path.normcase(entry.path):
                        continue

                    proposals.append(
                        OrganizationProposal(
                            source_path=entry.path,
                            filename=entry.name,
                            size_bytes=int(stat.st_size),
                            matched_rule=rule_desc,
                            target_folder_name=folder_Bucket,
                            proposed_destination=str(proposed_dest),
                            selected=True,
                        )
                    )
        except OSError:
            return []

        proposals.sort(key=lambda p: (p.target_folder_name, p.filename.lower()))
        return proposals

    def _classify_file(self, filename: str) -> Tuple[str, str]:
        name_low = filename.lower()
        ext = os.path.splitext(name_low)[1]

        for kw in self.UNIVERSITY_KEYWORDS:
            if kw in name_low:
                return "University", f"Naming pattern ('{kw}')"

        for kw in self.PROJECT_KEYWORDS:
            if kw in name_low:
                return "Projects", f"Project keyword ('{kw}')"

        cat = classify_extension(ext)
        if cat in self.STANDARD_FOLDERS:
            return cat, f"Extension rule ({ext or 'file'} -> {cat})"

        return "Documents", "Fallback organization rule"

    def execute_proposals(
        self, proposals: List[OrganizationProposal]
    ) -> Dict[str, object]:
        """Execute only user-selected proposals and record batch for one-click Undo."""
        moved = 0
        failed = 0
        errors: List[str] = []
        executed_pairs: List[Tuple[str, str]] = []

        for prop in proposals:
            if not prop.selected:
                continue
            target_dir = Path(prop.proposed_destination).parent
            target_dir.mkdir(parents=True, exist_ok=True)
            ok, result_msg = self.ops.move_item(prop.source_path, prop.proposed_destination)
            if ok:
                moved += 1
                executed_pairs.append((prop.source_path, result_msg))
            else:
                failed += 1
                errors.append(f"{prop.filename}: {result_msg}")

        if executed_pairs:
            self._last_batch_moves = executed_pairs

        return {
            "moved": moved,
            "failed": failed,
            "errors": errors,
        }

    def undo_last_batch(self) -> Tuple[int, List[str]]:
        """Reverse the most recently executed organization batch."""
        restored = 0
        errors: List[str] = []
        for orig_src, current_dst in reversed(self._last_batch_moves):
            dst_p = Path(current_dst)
            orig_p = Path(orig_src)
            if dst_p.exists() and not orig_p.exists():
                ok, msg = self.ops.move_item(dst_p, orig_p.parent)
                if ok:
                    restored += 1
                else:
                    errors.append(msg)
        self._last_batch_moves.clear()
        return restored, errors
