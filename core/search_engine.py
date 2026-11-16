"""
Universal Search Engine supporting both Mode A (Indexed SQLite/FTS5 Search)
and Mode B (Direct Real-Time Filesystem Search) with fuzzy matching,
content search, advanced category filters, search suggestions, and cancellation.
"""

from __future__ import annotations

import difflib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config.settings import FILE_CATEGORIES, SettingsManager
from core.drive_manager import DriveManager
from core.file_scanner import FileScanner, ScannedEntry
from database.database import LocalDatabase

QUICK_FILTER_MAP: Dict[str, str] = {
    "PDFs": "PDFs",
    "Images": "Images",
    "Videos": "Videos",
    "Audio": "Audio",
    "Documents": "Documents",
    "Archives": "Archives",
    "Executables": "Installers",
    "Programming": "Programming",
}


@dataclass
class SearchQuery:
    """Structured search query parameters across all filters."""

    text: str = ""
    exact_match: bool = False
    fuzzy_match: bool = False
    search_mode: str = "Direct"  # 'Direct' or 'Indexed'
    roots: List[str] = field(default_factory=list)
    extensions: List[str] = field(default_factory=list)
    category: str = "All"  # All, PDFs, Images, Videos, Audio, Documents, Archives, Executables, Programming
    min_size_bytes: Optional[int] = None
    max_size_bytes: Optional[int] = None
    modified_after: Optional[float] = None
    modified_before: Optional[float] = None
    created_after: Optional[float] = None
    created_before: Optional[float] = None
    content_query: str = ""
    include_dirs: bool = False
    sort_by: str = "name"  # 'name', 'size', 'mtime', 'type'
    sort_desc: bool = False
    limit: int = 5000


class SearchEngine:
    """Executes fast indexed or direct filesystem searches across C: and D:."""

    def __init__(
        self,
        db: Optional[LocalDatabase] = None,
        settings_mgr: Optional[SettingsManager] = None,
    ) -> None:
        self.db = db
        self.settings_mgr = settings_mgr or SettingsManager()
        self.scanner = FileScanner(self.settings_mgr)

    def search(
        self,
        query: SearchQuery,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[List[ScannedEntry], int, str], None]] = None,
    ) -> List[ScannedEntry]:
        """
        Execute search according to `query.search_mode`.
        Automatically falls back to Direct Search if Indexed Search is unavailable or empty.
        """
        if query.text.strip():
            self._record_history(query.text.strip())

        if query.search_mode == "Indexed" and self.db and self.db.is_available:
            indexed_results = self._search_indexed(query, cancel_check=cancel_check)
            if indexed_results or (self.db.query("SELECT COUNT(*) AS c FROM files")[0]["c"] > 0):
                return indexed_results

        return self._search_direct(
            query,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )

    def _search_indexed(
        self,
        query: SearchQuery,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> List[ScannedEntry]:
        """Search the SQLite index using FTS5 or indexed SQL columns."""
        assert self.db is not None
        clauses: List[str] = []
        params: List[Any] = []

        if not query.include_dirs:
            clauses.append("is_dir = 0")

        if query.roots:
            root_clauses = []
            for r in query.roots:
                norm_r = os.path.abspath(r)
                prefix = norm_r if norm_r.endswith(os.sep) else norm_r + os.sep
                root_clauses.append("(lower(path) = lower(?) OR lower(substr(path, 1, ?)) = lower(?))")
                params.extend([norm_r, len(prefix), prefix])
            clauses.append("(" + " OR ".join(root_clauses) + ")")

        q_text = query.text.strip().lower()
        if q_text and not query.fuzzy_match:
            if query.exact_match:
                clauses.append("name_lower = ?")
                params.append(q_text)
            else:
                clauses.append("name_lower LIKE ?")
                params.append(f"%{q_text}%")

        if query.extensions:
            norm_exts = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in query.extensions]
            placeholders = ",".join("?" for _ in norm_exts)
            clauses.append(f"extension IN ({placeholders})")
            params.extend(norm_exts)

        if query.category and query.category != "All":
            if query.category == "PDFs":
                clauses.append("extension = '.pdf'")
            elif query.category == "Recently Modified":
                clauses.append("mtime >= ?")
                params.append(time.time() - 7 * 86400)
            elif query.category == "Old Files":
                clauses.append("mtime <= ?")
                params.append(time.time() - 180 * 86400)
            else:
                mapped = QUICK_FILTER_MAP.get(query.category, query.category)
                clauses.append("category = ?")
                params.append(mapped)

        if query.min_size_bytes is not None:
            clauses.append("size >= ?")
            params.append(int(query.min_size_bytes))
        if query.max_size_bytes is not None:
            clauses.append("size <= ?")
            params.append(int(query.max_size_bytes))
        if query.modified_after is not None:
            clauses.append("mtime >= ?")
            params.append(float(query.modified_after))
        if query.modified_before is not None:
            clauses.append("mtime <= ?")
            params.append(float(query.modified_before))
        if query.created_after is not None:
            clauses.append("ctime >= ?")
            params.append(float(query.created_after))
        if query.created_before is not None:
            clauses.append("ctime <= ?")
            params.append(float(query.created_before))

        if query.content_query.strip():
            clauses.append("content_snippet LIKE ?")
            params.append(f"%{query.content_query.strip()}%")

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sort_col = {
            "name": "name_lower",
            "size": "size",
            "mtime": "mtime",
            "type": "extension",
        }.get(query.sort_by, "name_lower")
        sort_dir = "DESC" if query.sort_desc else "ASC"

        sql = f"""
            SELECT path, name, parent_dir, extension, category, size, mtime, ctime, atime, is_dir, is_hidden
            FROM files
            {where_sql}
            ORDER BY {sort_col} {sort_dir}
            LIMIT ?
        """
        params.append(int(query.limit))
        rows = self.db.query(sql, tuple(params))

        results: List[ScannedEntry] = []
        for r in rows:
            if cancel_check and cancel_check():
                break
            entry = ScannedEntry(
                path=r["path"],
                name=r["name"],
                parent_dir=r["parent_dir"],
                extension=r["extension"],
                category=r["category"],
                size=int(r["size"]),
                mtime=float(r["mtime"]),
                ctime=float(r["ctime"]),
                atime=float(r["atime"]),
                is_dir=bool(r["is_dir"]),
                is_hidden=bool(r["is_hidden"]),
            )
            if query.fuzzy_match and q_text:
                if not self._matches_fuzzy(q_text, entry.name.lower()):
                    continue
            # If content_query wasn't stored in DB snippet, verify on disk if needed
            results.append(entry)
        return results

    DIRECT_SKIP_DIRS = {
        "node_modules",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "site-packages",
        "_internal",
        "msys64",
        "AppData",
        "ProgramData",
        "$Recycle.Bin",
        "System Volume Information",
        "WinSxS",
        "oracle11g",
        "OracleXE112_Win64",
        "Visual Studio",
        "Microsoft VS Code",
        "xampp",
        "SQL Server",
        "SQL2025",
        "mssql2012-sp1-en",
        "Antigravity IDE",
        "Netmarble Game",
        "Netmarble Launcher",
        "Thonny",
        "Dbeaver",
        "cursor",
    }

    def _resolve_default_roots(self) -> List[str]:
        default_drv = self.settings_mgr.settings.default_drive
        if default_drv and len(default_drv.strip()) > 3 and os.path.exists(default_drv):
            return [default_drv]
        detected = [d.mountpoint for d in DriveManager().detect_drives() if os.path.exists(d.mountpoint)]
        return detected or [default_drv]

    def _search_direct(
        self,
        query: SearchQuery,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[List[ScannedEntry], int, str], None]] = None,
    ) -> List[ScannedEntry]:
        """Stream directly from the live filesystem without requiring SQLite."""
        roots = query.roots or self._resolve_default_roots()
        q_text = query.text.strip().lower()
        norm_exts = {
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in query.extensions
            if e.strip()
        }
        content_q = query.content_query.strip().lower()
        now = time.time()
        last_progress_ts = now
        scanned_count = 0

        results: List[ScannedEntry] = []
        seen_paths: set[str] = set()

        # Interleave user folders and all drive roots in a single shared BFS queue
        bfs_roots: List[str] = []
        any_drive_root = False
        for r in roots:
            norm_r = os.path.abspath(r)
            if len(norm_r) <= 3:
                any_drive_root = True
                if norm_r.upper().startswith("C:"):
                    home = str(Path.home())
                    for sub in ("Desktop", "Documents", "Downloads"):
                        cand = os.path.join(home, sub)
                        if os.path.isdir(cand):
                            bfs_roots.append(cand)
            if os.path.exists(norm_r):
                bfs_roots.append(norm_r)

        skip_set = self.DIRECT_SKIP_DIRS if any_drive_root else None
        emitted_first = False
        for entry in self.scanner.iter_directory(
            bfs_roots,
            recursive=True,
            include_dirs=query.include_dirs,
            cancel_check=cancel_check,
            skip_dir_names=skip_set,
        ):
            if cancel_check and cancel_check():
                break
            norm_p = os.path.normcase(entry.path)
            if norm_p in seen_paths:
                continue
            seen_paths.add(norm_p)
            scanned_count += 1

            if not query.include_dirs and entry.is_dir:
                continue

            matched = True
            if q_text:
                name_low = entry.name.lower()
                if query.exact_match:
                    if name_low != q_text:
                        matched = False
                elif query.fuzzy_match:
                    if not self._matches_fuzzy(q_text, name_low):
                        matched = False
                else:
                    if q_text not in name_low:
                        matched = False

            if matched and norm_exts and entry.extension not in norm_exts:
                matched = False

            if matched and query.category and query.category != "All":
                if query.category == "PDFs" and entry.extension != ".pdf":
                    matched = False
                elif query.category == "Recently Modified" and entry.mtime < (now - 7 * 86400):
                    matched = False
                elif query.category == "Old Files" and entry.mtime > (now - 180 * 86400):
                    matched = False
                elif query.category not in ("PDFs", "Recently Modified", "Old Files"):
                    mapped = QUICK_FILTER_MAP.get(query.category, query.category)
                    if entry.category != mapped:
                        matched = False

            if matched and query.min_size_bytes is not None and entry.size < query.min_size_bytes:
                matched = False
            if matched and query.max_size_bytes is not None and entry.size > query.max_size_bytes:
                matched = False
            if matched and query.modified_after is not None and entry.mtime < query.modified_after:
                matched = False
            if matched and query.modified_before is not None and entry.mtime > query.modified_before:
                matched = False
            if matched and query.created_after is not None and entry.ctime < query.created_after:
                matched = False
            if matched and query.created_before is not None and entry.ctime > query.created_before:
                matched = False

            if matched and content_q:
                if entry.is_dir or not self._file_contains_text(entry.path, content_q, entry.size):
                    matched = False

            if matched:
                results.append(entry)

            if progress_callback and (
                (matched and not emitted_first)
                or (matched and time.time() - last_progress_ts >= 0.2)
                or scanned_count % 2000 == 0
            ):
                if matched:
                    emitted_first = True
                last_progress_ts = time.time()
                progress_callback(list(results), scanned_count, entry.parent_dir)

            if len(results) >= query.limit:
                break

        key_fn = {
            "name": lambda e: e.name.lower(),
            "size": lambda e: e.size,
            "mtime": lambda e: e.mtime,
            "type": lambda e: e.extension,
        }.get(query.sort_by, lambda e: e.name.lower())
        results.sort(key=key_fn, reverse=query.sort_desc)
        return results

    @staticmethod
    def _matches_fuzzy(pattern: str, candidate: str) -> bool:
        if pattern in candidate:
            return True
        stem = os.path.splitext(candidate)[0]
        ratio = difflib.SequenceMatcher(None, pattern, stem).ratio()
        if ratio >= 0.62:
            return True
        # Subsequence check (like Raycast / Everything fuzzy match)
        it = iter(candidate)
        return all(ch in it for ch in pattern)

    @staticmethod
    def _file_contains_text(path: str, needle_lower: str, size: int) -> bool:
        if size > 10 * 1024 * 1024:  # Skip files > 10MB during live content scan
            return False
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    if needle_lower in chunk.lower():
                        return True
        except Exception:
            return False
        return False

    def get_suggestions(self, prefix: str, limit: int = 8) -> List[str]:
        """Return search suggestions combining history and indexed filenames."""
        prefix_low = prefix.strip().lower()
        suggestions: List[str] = []
        for item in self.settings_mgr.settings.search_history:
            if not prefix_low or prefix_low in item.lower():
                if item not in suggestions:
                    suggestions.append(item)
        if self.db and self.db.is_available and prefix_low:
            rows = self.db.query(
                "SELECT DISTINCT name FROM files WHERE name_lower LIKE ? LIMIT ?",
                (f"{prefix_low}%", limit),
            )
            for r in rows:
                if r["name"] not in suggestions:
                    suggestions.append(r["name"])
        return suggestions[:limit]

    def _record_history(self, query_text: str) -> None:
        hist = self.settings_mgr.settings.search_history
        if query_text in hist:
            hist.remove(query_text)
        hist.insert(0, query_text)
        del hist[50:]
        self.settings_mgr.save()

    def save_search(self, name: str, query: SearchQuery) -> None:
        """Persist a named search configuration."""
        entry = {
            "name": name,
            "text": query.text,
            "category": query.category,
            "extensions": query.extensions,
            "min_size_bytes": query.min_size_bytes,
            "fuzzy_match": query.fuzzy_match,
            "search_mode": query.search_mode,
        }
        saved = self.settings_mgr.settings.saved_searches
        saved = [s for s in saved if s.get("name") != name]
        saved.append(entry)
        self.settings_mgr.settings.saved_searches = saved
        self.settings_mgr.save()
