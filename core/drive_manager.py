"""
Drive detection and real storage capacity analyzer for Windows (C:\\, D:\\, etc.)
and POSIX environments. Uses psutil when available and falls back to ctypes/shutil.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import string
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None


@dataclass
class DriveInfo:
    """Real filesystem metrics for a single mounted drive or volume."""

    name: str
    mountpoint: str
    fstype: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float
    is_ready: bool = True
    label: str = ""
    indexed_files: Optional[int] = None
    indexed_folders: Optional[int] = None
    last_scan_time: Optional[float] = None
    stats_source: str = "Estimated (OS Volume)"  # 'Estimated (OS Volume)', 'Scanned', 'Indexed'

    @property
    def total_gb(self) -> float:
        return round(self.total_bytes / (1024 ** 3), 2)

    @property
    def used_gb(self) -> float:
        return round(self.used_bytes / (1024 ** 3), 2)

    @property
    def free_gb(self) -> float:
        return round(self.free_bytes / (1024 ** 3), 2)


class DriveManager:
    """Detects available drives and prioritizes C:\\ and D:\\ on Windows."""

    def __init__(self, custom_roots: Optional[List[str]] = None) -> None:
        self.custom_roots = custom_roots or []

    def detect_drives(self) -> List[DriveInfo]:
        """Return list of real available drives prioritized with C:\\ and D:\\ first."""
        drives: List[DriveInfo] = []
        seen_mounts: set[str] = set()

        if self.custom_roots:
            for root in self.custom_roots:
                info = self.get_drive_info(root)
                if info:
                    drives.append(info)
            return drives

        if sys.platform == "win32":
            candidate_mounts = self._detect_windows_mounts()
            for mount, fstype in candidate_mounts:
                norm = os.path.normcase(mount)
                if norm in seen_mounts:
                    continue
                info = self.get_drive_info(mount, fstype=fstype)
                if info:
                    seen_mounts.add(norm)
                    drives.append(info)
            # Prioritize C:\ and D:\ first
            drives.sort(
                key=lambda d: (
                    0 if d.mountpoint.upper().startswith("C:")
                    else 1 if d.mountpoint.upper().startswith("D:")
                    else 2,
                    d.mountpoint.upper(),
                )
            )
            return drives

        # Non-Windows fallback (for automated testing and Linux workstation verification)
        if psutil is not None:
            try:
                for part in psutil.disk_partitions(all=False):
                    info = self.get_drive_info(part.mountpoint, fstype=part.fstype)
                    if info and info.mountpoint not in seen_mounts:
                        seen_mounts.add(info.mountpoint)
                        drives.append(info)
            except Exception:
                pass

        if not drives:
            root_info = self.get_drive_info("/")
            if root_info:
                drives.append(root_info)
            home_str = str(Path.home())
            if home_str != "/" and Path(home_str).exists():
                home_info = self.get_drive_info(home_str, label="Home Workspace")
                if home_info:
                    drives.append(home_info)

        return drives

    def _detect_windows_mounts(self) -> List[tuple[str, str]]:
        """Use psutil or Win32 GetLogicalDrives bitmask to find mounted drives."""
        results: List[tuple[str, str]] = []
        if psutil is not None:
            try:
                for p in psutil.disk_partitions(all=False):
                    if p.mountpoint:
                        results.append((p.mountpoint, p.fstype or "NTFS"))
                if results:
                    return results
            except Exception:
                pass

        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for idx, letter in enumerate(string.ascii_uppercase):
                if bitmask & (1 << idx):
                    mount = f"{letter}:\\\\"
                    if os.path.exists(mount):
                        results.append((mount, "NTFS"))
        except Exception:
            for letter in ("C", "D", "E", "F"):
                mount = f"{letter}:\\\\"
                if os.path.exists(mount):
                    results.append((mount, "NTFS"))
        return results

    def get_drive_info(
        self,
        mountpoint: str | Path,
        fstype: str = "Filesystem",
        label: str = "",
    ) -> Optional[DriveInfo]:
        """Query real total/used/free bytes for a given mountpoint or directory."""
        mount_str = str(mountpoint)
        try:
            if psutil is not None:
                usage = psutil.disk_usage(mount_str)
                total_b = int(usage.total)
                used_b = int(usage.used)
                free_b = int(usage.free)
                pct = float(usage.percent)
            else:
                du = shutil.disk_usage(mount_str)
                total_b = int(du.total)
                used_b = int(du.used)
                free_b = int(du.free)
                pct = round((used_b / total_b) * 100.0, 2) if total_b > 0 else 0.0

            disp_name = label or mount_str
            if sys.platform == "win32" and len(mount_str) >= 2 and mount_str[1] == ":":
                vol_label = self._get_windows_volume_label(mount_str[:3])
                disp_name = f"{mount_str[:2]} ({vol_label})" if vol_label else f"Local Disk ({mount_str[:2]})"

            return DriveInfo(
                name=disp_name,
                mountpoint=mount_str,
                fstype=fstype,
                total_bytes=total_b,
                used_bytes=used_b,
                free_bytes=free_b,
                percent_used=pct,
                is_ready=True,
                label=label or disp_name,
            )
        except OSError:
            return None

    @staticmethod
    def _get_windows_volume_label(drive_root: str) -> str:
        if sys.platform != "win32":
            return ""
        try:
            vol_buf = ctypes.create_unicode_buffer(261)
            fs_buf = ctypes.create_unicode_buffer(261)
            ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive_root),
                vol_buf,
                ctypes.sizeof(vol_buf),
                None,
                None,
                None,
                fs_buf,
                ctypes.sizeof(fs_buf),
            )
            return vol_buf.value
        except Exception:
            return ""

    def get_combined_summary(self, drives: List[DriveInfo]) -> Dict[str, object]:
        """Aggregate storage statistics across multiple drives."""
        total_b = sum(d.total_bytes for d in drives)
        used_b = sum(d.used_bytes for d in drives)
        free_b = sum(d.free_bytes for d in drives)
        pct = round((used_b / total_b) * 100.0, 2) if total_b > 0 else 0.0
        return {
            "drive_count": len(drives),
            "total_bytes": total_b,
            "used_bytes": used_b,
            "free_bytes": free_b,
            "percent_used": pct,
        }
