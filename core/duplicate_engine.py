"""
Multistage SHA-256 Duplicate Detection Engine.
Stage 1: Group candidate files by exact byte size (> 0 bytes).
Stage 2: Discard unique file sizes immediately.
Stage 3: Compute fast 64 KB pre-hash (first + last 32 KB) for large files to prune non-matches.
Stage 4: Compute full streaming SHA-256 hash on remaining candidates.
Stage 5: Group verified identical files and calculate recoverable storage.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config.settings import SettingsManager
from core.file_scanner import FileScanner, ScannedEntry


@dataclass
class DuplicateGroup:
    """Represents a verified group of byte-identical files sharing a SHA-256 hash."""

    sha256: str
    file_size: int
    files: List[ScannedEntry] = field(default_factory=list)

    @property
    def copies_count(self) -> int:
        return len(self.files)

    @property
    def recoverable_bytes(self) -> int:
        return max(0, (len(self.files) - 1) * self.file_size)


@dataclass
class DuplicateScanReport:
    """Complete result of a multistage duplicate scan."""

    groups: List[DuplicateGroup] = field(default_factory=list)
    total_duplicate_files: int = 0
    total_recoverable_bytes: int = 0
    candidates_hashed: int = 0
    cancelled: bool = False


class DuplicateEngine:
    """Reliable content-based duplicate file detector."""

    def __init__(self, settings_mgr: Optional[SettingsManager] = None) -> None:
        self.settings_mgr = settings_mgr or SettingsManager()
        self.scanner = FileScanner(self.settings_mgr)

    @staticmethod
    def compute_sha256(
        file_path: str | Path,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        """Compute full SHA-256 digest using 1 MB streaming chunks."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while True:
                    if cancel_check and cancel_check():
                        return None
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:
            return None

    @staticmethod
    def _compute_partial_hash(file_path: str | Path, size: int) -> Optional[str]:
        """Compute fast head+tail 64 KB SHA-256 digest to eliminate non-matching large files."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                head = f.read(32768)
                hasher.update(head)
                if size > 65536:
                    f.seek(max(0, size - 32768))
                    tail = f.read(32768)
                    hasher.update(tail)
            return hasher.hexdigest()
        except OSError:
            return None

    def find_duplicates(
        self,
        roots: List[str | Path],
        min_size_bytes: int = 1,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> DuplicateScanReport:
        """Execute the 6-stage duplicate detection pipeline."""
        report = DuplicateScanReport()

        # Stage 1: Group files by exact byte size
        size_buckets: Dict[int, List[ScannedEntry]] = {}
        scanned_count = 0
        for root in roots:
            if not os.path.exists(root):
                continue
            for entry in self.scanner.iter_directory(
                root, recursive=True, include_dirs=False, cancel_check=cancel_check
            ):
                if cancel_check and cancel_check():
                    report.cancelled = True
                    return report
                if entry.size < min_size_bytes:
                    continue
                size_buckets.setdefault(entry.size, []).append(entry)
                scanned_count += 1
                if progress_callback and scanned_count % 300 == 0:
                    progress_callback("Grouping by size...", scanned_count, 0)

        # Stage 2: Ignore files with unique sizes
        candidate_buckets = {
            sz: entries for sz, entries in size_buckets.items() if len(entries) > 1
        }
        total_candidates = sum(len(v) for v in candidate_buckets.values())

        # Stage 3 & 4: Partial hash filter (for files > 128 KB) followed by full SHA-256
        hash_groups: Dict[tuple[int, str], List[ScannedEntry]] = {}
        processed = 0

        for sz, entries in sorted(candidate_buckets.items(), key=lambda x: x[0], reverse=True):
            if cancel_check and cancel_check():
                report.cancelled = True
                return report

            if sz > 131072:
                partial_map: Dict[str, List[ScannedEntry]] = {}
                for e in entries:
                    ph = self._compute_partial_hash(e.path, sz)
                    if ph:
                        partial_map.setdefault(ph, []).append(e)
                refined_entries = [
                    e for group in partial_map.values() if len(group) > 1 for e in group
                ]
            else:
                refined_entries = entries

            for e in refined_entries:
                if cancel_check and cancel_check():
                    report.cancelled = True
                    return report
                digest = self.compute_sha256(e.path, cancel_check=cancel_check)
                processed += 1
                report.candidates_hashed += 1
                if digest:
                    hash_groups.setdefault((sz, digest), []).append(e)
                if progress_callback and processed % 25 == 0:
                    progress_callback("Computing SHA-256 hashes...", processed, total_candidates)

        # Stage 5 & 6: Group identical files and calculate recoverable storage
        for (sz, digest), group_entries in hash_groups.items():
            if len(group_entries) > 1:
                group_entries.sort(key=lambda x: x.mtime)
                grp = DuplicateGroup(sha256=digest, file_size=sz, files=group_entries)
                report.groups.append(grp)
                report.total_duplicate_files += len(group_entries) - 1
                report.total_recoverable_bytes += grp.recoverable_bytes

        report.groups.sort(key=lambda g: g.recoverable_bytes, reverse=True)
        return report
