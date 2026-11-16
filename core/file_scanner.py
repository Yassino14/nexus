"""
Streaming filesystem scanner using os.scandir with junction/symlink protection,
permission error reporting, and low memory footprint.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Set

from config.settings import SettingsManager, classify_extension


@dataclass
class ScannedEntry:
    """Lightweight representation of a scanned file or directory."""

    path: str
    name: str
    parent_dir: str
    extension: str
    category: str
    size: int
    mtime: float
    ctime: float
    atime: float
    is_dir: bool
    is_hidden: bool = False


@dataclass
class ScanSummary:
    """Real filesystem scan results including inaccessible directory diagnostics."""

    root_path: str
    files_count: int = 0
    folders_count: int = 0
    total_bytes: int = 0
    inaccessible_paths: List[str] = field(default_factory=list)
    extension_bytes: Dict[str, int] = field(default_factory=dict)
    extension_counts: Dict[str, int] = field(default_factory=dict)
    category_bytes: Dict[str, int] = field(default_factory=dict)
    age_buckets: Dict[str, int] = field(
        default_factory=lambda: {
            "< 7 Days": 0,
            "7–30 Days": 0,
            "1–6 Months": 0,
            "6–12 Months": 0,
            "> 1 Year": 0,
        }
    )
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    cancelled: bool = False


class FileScanner:
    """High-speed streaming filesystem scanner."""

    LOW_PRIORITY_DIRS: Set[str] = {
        "node_modules",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "site-packages",
        "AppData",
        "msys64",
        "_internal",
        "ProgramData",
        "oracle11g",
        "OracleXE112_Win64",
        "Visual Studio",
        "Microsoft VS Code",
        "xampp",
        "SQL Server",
        "SQL2025",
        "Antigravity IDE",
        "Netmarble Game",
    }

    def __init__(self, settings_mgr: Optional[SettingsManager] = None) -> None:
        self.settings_mgr = settings_mgr or SettingsManager()

    def iter_directory(
        self,
        root_path: str | Path | List[str],
        recursive: bool = True,
        include_dirs: bool = True,
        cancel_check: Optional[Callable[[], bool]] = None,
        inaccessible_log: Optional[List[str]] = None,
        skip_dir_names: Optional[Set[str]] = None,
    ) -> Iterator[ScannedEntry]:
        """
        Stream entries inside `root_path` (or multiple roots simultaneously)
        using breadth-first traversal (BFS) so shallow user files and folders
        across all drives are discovered immediately before descending into deep trees.
        """
        if isinstance(root_path, list):
            initial_roots = [os.path.abspath(str(p)) for p in root_path if os.path.exists(p)]
        else:
            initial_roots = [os.path.abspath(str(root_path))]
        queue: deque[str] = deque(initial_roots)
        seen_dirs: set[str] = set()
        visited_realpaths: set[str] = set()
        follow_links = self.settings_mgr.settings.follow_symlinks
        show_hidden = self.settings_mgr.settings.show_hidden_files

        while queue:
            if cancel_check and cancel_check():
                return
            current_dir = queue.popleft()
            norm_cur = os.path.normcase(current_dir)
            if norm_cur in seen_dirs:
                continue
            seen_dirs.add(norm_cur)
            if self.settings_mgr.is_path_excluded(current_dir):
                continue

            if follow_links:
                real_dir = os.path.realpath(current_dir)
                if real_dir in visited_realpaths:
                    continue
                visited_realpaths.add(real_dir)

            high_prio_dirs: List[str] = []
            low_prio_dirs: List[str] = []

            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        if cancel_check and cancel_check():
                            return
                        full_path = entry.path
                        if self.settings_mgr.is_path_excluded(full_path):
                            continue
                        try:
                            is_link_or_junc = entry.is_symlink() or (
                                hasattr(entry, "is_junction") and entry.is_junction()
                            )
                            if is_link_or_junc and not follow_links:
                                continue
                            is_dir = entry.is_dir(follow_symlinks=follow_links)
                            stat = entry.stat(follow_symlinks=follow_links)
                        except PermissionError:
                            if inaccessible_log is not None:
                                inaccessible_log.append(full_path)
                            continue
                        except OSError:
                            continue

                        is_hidden = entry.name.startswith(".") or bool(
                            getattr(stat, "st_file_attributes", 0) & 0x2
                        )
                        if not show_hidden and is_hidden:
                            continue

                        if is_dir:
                            if recursive:
                                if skip_dir_names and entry.name in skip_dir_names:
                                    pass
                                elif entry.name in self.LOW_PRIORITY_DIRS:
                                    low_prio_dirs.append(full_path)
                                else:
                                    high_prio_dirs.append(full_path)
                            if include_dirs:
                                yield ScannedEntry(
                                    path=full_path,
                                    name=entry.name,
                                    parent_dir=current_dir,
                                    extension="",
                                    category="Folder",
                                    size=0,
                                    mtime=float(stat.st_mtime),
                                    ctime=float(getattr(stat, "st_ctime", stat.st_mtime)),
                                    atime=float(getattr(stat, "st_atime", stat.st_mtime)),
                                    is_dir=True,
                                    is_hidden=is_hidden,
                                )
                        else:
                            ext = os.path.splitext(entry.name)[1].lower()
                            yield ScannedEntry(
                                path=full_path,
                                name=entry.name,
                                parent_dir=current_dir,
                                extension=ext,
                                category=classify_extension(ext),
                                size=int(stat.st_size),
                                mtime=float(stat.st_mtime),
                                ctime=float(getattr(stat, "st_ctime", stat.st_mtime)),
                                atime=float(getattr(stat, "st_atime", stat.st_mtime)),
                                is_dir=False,
                                is_hidden=is_hidden,
                            )
                if recursive:
                    queue.extend(high_prio_dirs)
                    queue.extend(low_prio_dirs)
            except PermissionError:
                if inaccessible_log is not None:
                    inaccessible_log.append(current_dir)
            except OSError:
                continue

    def scan_summary(
        self,
        root_path: str | Path,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[ScanSummary], None]] = None,
    ) -> ScanSummary:
        """Compute aggregate statistics for a drive or directory."""
        summary = ScanSummary(root_path=os.path.abspath(str(root_path)))
        now = time.time()

        for idx, entry in enumerate(
            self.iter_directory(
                root_path,
                recursive=True,
                include_dirs=True,
                cancel_check=cancel_check,
                inaccessible_log=summary.inaccessible_paths,
            ),
            start=1,
        ):
            if entry.is_dir:
                summary.folders_count += 1
            else:
                summary.files_count += 1
                summary.total_bytes += entry.size
                ext_key = entry.extension or "(no ext)"
                summary.extension_bytes[ext_key] = summary.extension_bytes.get(ext_key, 0) + entry.size
                summary.extension_counts[ext_key] = summary.extension_counts.get(ext_key, 0) + 1
                summary.category_bytes[entry.category] = (
                    summary.category_bytes.get(entry.category, 0) + entry.size
                )

                age_days = max(0.0, (now - entry.mtime) / 86400.0)
                if age_days < 7:
                    summary.age_buckets["< 7 Days"] += 1
                elif age_days < 30:
                    summary.age_buckets["7–30 Days"] += 1
                elif age_days < 180:
                    summary.age_buckets["1–6 Months"] += 1
                elif age_days < 365:
                    summary.age_buckets["6–12 Months"] += 1
                else:
                    summary.age_buckets["> 1 Year"] += 1

            if progress_callback and idx % 500 == 0:
                progress_callback(summary)

        if cancel_check and cancel_check():
            summary.cancelled = True
        summary.completed_at = time.time()
        return summary
