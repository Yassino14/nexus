"""
Persistent local configuration and filesystem safety rules for NEXUS FILES.
All settings are stored offline as JSON on the user's local machine.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


def get_default_app_data_dir() -> Path:
    """Return local application data directory for Windows or POSIX fallback."""
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "NexusFiles"
    return Path.home() / ".nexus_files"


DEFAULT_PROTECTED_WINDOWS_DIRS: List[str] = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData\\Microsoft",
    "C:\\$Recycle.Bin",
    "C:\\System Volume Information",
    "C:\\Recovery",
    "D:\\$Recycle.Bin",
    "D:\\System Volume Information",
    "/proc",
    "/sys",
    "/dev",
]

FILE_CATEGORIES: Dict[str, List[str]] = {
    "Documents": [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".md", ".rtf", ".csv", ".odt", ".ods", ".epub",
    ],
    "Images": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
        ".ico", ".tif", ".tiff", ".heic", ".raw", ".psd",
    ],
    "Videos": [
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
    ],
    "Audio": [
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
    ],
    "Archives": [
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".tgz",
    ],
    "Installers": [
        ".exe", ".msi", ".msix", ".bat", ".cmd", ".ps1", ".dmg", ".deb", ".rpm",
    ],
    "Programming": [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs", ".cpp", ".c",
        ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".html", ".css", ".scss",
        ".sql", ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".sh",
        ".ipynb", ".r", ".dart", ".kt", ".swift",
    ],
}

EXTENSION_TO_CATEGORY: Dict[str, str] = {
    ext: cat for cat, exts in FILE_CATEGORIES.items() for ext in exts
}


def classify_extension(ext: str) -> str:
    """Return high-level category name for a file extension (e.g. '.pdf' -> 'Documents')."""
    norm = ext.lower() if ext.startswith(".") else f".{ext.lower()}" if ext else ""
    return EXTENSION_TO_CATEGORY.get(norm, "Other")


@dataclass
class AppSettings:
    """User-configurable settings persisted locally."""

    theme: str = "Dark Charcoal (Linear)"
    accent_color: str = "#6366F1"
    default_drive: str = "C:\\" if sys.platform == "win32" else str(Path.home())
    default_folder_view: str = "Detailed"  # Detailed, List, Grid
    default_search_mode: str = "Direct"    # Direct, Indexed
    database_enabled: bool = True
    database_location: str = ""
    excluded_directories: List[str] = field(
        default_factory=lambda: list(DEFAULT_PROTECTED_WINDOWS_DIRS)
    )
    show_hidden_files: bool = False
    background_monitoring: bool = False
    indexing_max_files: int = 1_000_000
    max_worker_threads: int = 4
    content_indexing_enabled: bool = False
    max_content_index_size_kb: int = 512
    default_backup_location: str = ""
    confirm_batch_operations: bool = True
    confirm_deletions: bool = True
    use_recycle_bin: bool = True
    follow_symlinks: bool = False
    saved_searches: List[Dict[str, object]] = field(default_factory=list)
    search_history: List[str] = field(default_factory=list)
    preferred_editor: str = "code"

    def __post_init__(self) -> None:
        app_dir = get_default_app_data_dir()
        if not self.database_location:
            self.database_location = str(app_dir / "nexus_index.sqlite3")
        if not self.default_backup_location:
            self.default_backup_location = str(app_dir / "backups")


class SettingsManager:
    """Manages loading, validating, and saving AppSettings to disk."""

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        self.app_dir = get_default_app_data_dir()
        self.config_path = (
            Path(config_path)
            if config_path
            else self.app_dir / "settings.json"
        )
        self.settings = AppSettings()
        self.load()

    def load(self) -> AppSettings:
        """Load settings from JSON if present; otherwise keep safe defaults."""
        try:
            if self.config_path.exists():
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                valid_keys = set(AppSettings.__dataclass_fields__.keys())
                filtered = {k: v for k, v in raw.items() if k in valid_keys}
                self.settings = AppSettings(**filtered)
        except Exception:
            self.settings = AppSettings()
        return self.settings

    def save(self) -> bool:
        """Persist current settings atomically to local JSON file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.config_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(asdict(self.settings), indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self.config_path)
            return True
        except Exception:
            return False

    def reset_to_defaults(self) -> AppSettings:
        """Restore factory settings and persist."""
        self.settings = AppSettings()
        self.save()
        return self.settings

    def is_path_excluded(self, target_path: str | Path) -> bool:
        """Return True if target_path is the internal SQLite index or falls under any excluded directory."""
        norm_target = os.path.normcase(os.path.abspath(str(target_path)))
        if self.settings.database_location:
            norm_db = os.path.normcase(os.path.abspath(self.settings.database_location))
            if norm_target == norm_db or norm_target.startswith(norm_db + "-"):
                return True
        for excl in self.settings.excluded_directories:
            if not excl:
                continue
            norm_excl = os.path.normcase(os.path.abspath(excl))
            if norm_target == norm_excl or norm_target.startswith(norm_excl + os.sep):
                return True
        return False

    def is_system_protected_path(self, target_path: str | Path) -> bool:
        """
        Safety guard against modifying critical Windows system directories or drive roots.
        """
        raw_str = str(target_path).strip()
        if len(raw_str) <= 3 and (
            raw_str.endswith(":\\")
            or raw_str.endswith(":/")
            or raw_str == "/"
            or (len(raw_str) == 2 and raw_str[1] == ":")
        ):
            return True
        norm_win = raw_str.replace("/", "\\").lower().rstrip("\\")
        win_critical = (
            "c:\\windows",
            "c:\\program files",
            "c:\\program files (x86)",
            "c:\\system volume information",
            "c:\\$recycle.bin",
            "d:\\system volume information",
            "d:\\$recycle.bin",
        )
        for wroot in win_critical:
            if norm_win == wroot or norm_win.startswith(wroot + "\\"):
                return True

        norm_target = os.path.normcase(os.path.abspath(raw_str))
        if os.path.dirname(norm_target) == norm_target:
            return True
        posix_critical = ("/bin", "/sbin", "/usr", "/etc", "/proc", "/sys", "/dev")
        for root in posix_critical:
            if norm_target == root or norm_target.startswith(root + os.sep):
                return True
        return False
