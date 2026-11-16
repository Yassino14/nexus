"""
Modern unicode glyph & badge icon provider for files, extensions, and navigation items.
"""

from __future__ import annotations

from typing import Dict

EXTENSION_GLYPHS: Dict[str, str] = {
    ".pdf": "📕",
    ".doc": "📘",
    ".docx": "📘",
    ".xls": "📗",
    ".xlsx": "📗",
    ".csv": "📊",
    ".ppt": "📙",
    ".pptx": "📙",
    ".txt": "📄",
    ".md": "📝",
    ".py": "🐍",
    ".js": "🟨",
    ".ts": "🔷",
    ".json": "⚙️",
    ".html": "🌐",
    ".css": "🎨",
    ".java": "☕",
    ".cs": "🟣",
    ".cpp": "💠",
    ".c": "💠",
    ".sql": "🗄️",
    ".zip": "📦",
    ".rar": "📦",
    ".7z": "📦",
    ".tar": "📦",
    ".gz": "📦",
    ".exe": "⚡",
    ".msi": "⚡",
    ".bat": "🖥️",
    ".png": "🖼️",
    ".jpg": "🖼️",
    ".jpeg": "🖼️",
    ".gif": "🖼️",
    ".svg": "🖼️",
    ".mp4": "🎬",
    ".mkv": "🎬",
    ".mov": "🎬",
    ".mp3": "🎵",
    ".wav": "🎵",
    ".flac": "🎵",
}

NAV_ICONS: Dict[str, str] = {
    "Dashboard": "◫",
    "File Explorer": "📁",
    "Global Search": "⌕",
    "Disk Analyzer": "◔",
    "Duplicate Finder": "❐",
    "Large Files": "▲",
    "Smart Organizer": "✦",
    "File Inspector": "ⓘ",
    "Project Finder": "⌘",
    "Recent Activity": "⟳",
    "Folder Comparison": "⇄",
    "Settings": "⚙",
}


def get_file_glyph(extension: str, is_dir: bool = False) -> str:
    """Return a clean visual icon glyph for a folder or file extension."""
    if is_dir:
        return "📁"
    ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}" if extension else ""
    return EXTENSION_GLYPHS.get(ext, "📄")


def format_bytes(num_bytes: int | float) -> str:
    """Human-readable byte size formatter (B, KB, MB, GB, TB)."""
    val = float(max(0, num_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024.0 or unit == "TB":
            return f"{val:.0f} B" if unit == "B" else f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} TB"
