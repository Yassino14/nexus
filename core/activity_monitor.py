"""
Resource-Efficient Optional Filesystem Activity Monitor.
Uses `watchdog` when installed, and includes a lightweight snapshot/diff monitor
fallback so new, modified, renamed, and created folders are tracked reliably
even when background services or optional packages are absent.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.observers import Observer  # type: ignore
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object
    Observer = None


@dataclass
class ActivityEvent:
    """Single filesystem change event."""

    event_type: str  # 'Created', 'Modified', 'Renamed', 'Deleted', 'New Folder', 'Indexed'
    path: str
    dest_path: str = ""
    extension: str = ""
    drive: str = ""
    is_dir: bool = False
    timestamp: float = field(default_factory=time.time)


class ActivityMonitor:
    """Configurable, low-overhead filesystem activity tracker."""

    def __init__(self, max_events: int = 1000) -> None:
        self.max_events = max_events
        self.events: List[ActivityEvent] = []
        self._lock = threading.RLock()
        self._running = False
        self._observer: Any = None
        self._poll_thread: Optional[threading.Thread] = None
        self._watched_paths: List[str] = []
        self._snapshots: Dict[str, Dict[str, tuple[float, int, bool]]] = {}
        self.on_event: Optional[Callable[[ActivityEvent], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, paths: List[str | Path]) -> bool:
        """Start monitoring `paths` in background."""
        self.stop()
        self._watched_paths = [os.path.abspath(str(p)) for p in paths if os.path.exists(p)]
        if not self._watched_paths:
            return False

        self._running = True
        if WATCHDOG_AVAILABLE and Observer is not None:
            try:
                self._observer = Observer()
                handler = self._build_watchdog_handler()
                for p in self._watched_paths:
                    self._observer.schedule(handler, p, recursive=True)
                self._observer.start()
                return True
            except Exception:
                self._observer = None

        # Lightweight polling snapshot fallback
        for p in self._watched_paths:
            self._snapshots[p] = self._take_snapshot(p)
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        return True

    def stop(self) -> None:
        """Stop all background monitoring cleanly."""
        self._running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None
        if self._poll_thread is not None and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.5)
        self._poll_thread = None

    def record_event(
        self,
        event_type: str,
        path: str,
        dest_path: str = "",
        is_dir: bool = False,
    ) -> ActivityEvent:
        """Record an event manually or from a monitor callback."""
        abs_p = os.path.abspath(path)
        drive = os.path.splitdrive(abs_p)[0] or "/"
        ext = "" if is_dir else os.path.splitext(abs_p)[1].lower()
        ev = ActivityEvent(
            event_type=event_type,
            path=abs_p,
            dest_path=os.path.abspath(dest_path) if dest_path else "",
            extension=ext,
            drive=drive,
            is_dir=is_dir,
        )
        with self._lock:
            self.events.insert(0, ev)
            del self.events[self.max_events :]
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception:
                pass
        return ev

    def poll_once(self) -> List[ActivityEvent]:
        """Perform a single diff pass over watched paths (used by fallback thread and tests)."""
        detected: List[ActivityEvent] = []
        for root in list(self._watched_paths):
            old_snap = self._snapshots.get(root, {})
            new_snap = self._take_snapshot(root)
            self._snapshots[root] = new_snap

            old_keys = set(old_snap.keys())
            new_keys = set(new_snap.keys())

            added = new_keys - old_keys
            removed = old_keys - new_keys

            # Detect renames when an added file and removed file share identical (mtime, size, is_dir)
            unmatched_added = set(added)
            for rem_path in removed:
                r_mtime, r_size, r_isdir = old_snap[rem_path]
                matched_dest = None
                for add_path in list(unmatched_added):
                    a_mtime, a_size, a_isdir = new_snap[add_path]
                    if a_isdir == r_isdir and a_size == r_size and abs(a_mtime - r_mtime) < 2.0:
                        matched_dest = add_path
                        unmatched_added.remove(add_path)
                        break
                if matched_dest:
                    detected.append(self.record_event("Renamed", rem_path, dest_path=matched_dest, is_dir=r_isdir))
                else:
                    detected.append(self.record_event("Deleted", rem_path, is_dir=r_isdir))

            for add_path in unmatched_added:
                _, _, a_isdir = new_snap[add_path]
                ev_type = "New Folder" if a_isdir else "Created"
                detected.append(self.record_event(ev_type, add_path, is_dir=a_isdir))

            for common_path in old_keys & new_keys:
                o_mtime, o_size, o_isdir = old_snap[common_path]
                n_mtime, n_size, _ = new_snap[common_path]
                if not o_isdir and (n_size != o_size or abs(n_mtime - o_mtime) > 0.001):
                    detected.append(self.record_event("Modified", common_path, is_dir=False))

        return detected

    def get_filtered_events(
        self,
        drive_filter: str = "",
        directory_filter: str = "",
        extension_filter: str = "",
        since_timestamp: Optional[float] = None,
    ) -> List[ActivityEvent]:
        """Filter recorded activity events by drive, directory, extension, and date."""
        with self._lock:
            snapshot = list(self.events)

        results: List[ActivityEvent] = []
        ext_norm = extension_filter.strip().lower()
        if ext_norm and not ext_norm.startswith("."):
            ext_norm = "." + ext_norm
        dir_norm = os.path.normcase(os.path.abspath(directory_filter)) if directory_filter.strip() else ""

        for ev in snapshot:
            if drive_filter and drive_filter != "All":
                if not ev.path.upper().startswith(drive_filter.upper()):
                    continue
            if dir_norm:
                if not os.path.normcase(ev.path).startswith(dir_norm):
                    continue
            if ext_norm and ev.extension != ext_norm:
                continue
            if since_timestamp is not None and ev.timestamp < since_timestamp:
                continue
            results.append(ev)
        return results

    def _poll_loop(self) -> None:
        while self._running:
            time.sleep(1.5)
            if not self._running:
                break
            self.poll_once()

    @staticmethod
    def _take_snapshot(root: str, max_items: int = 10000) -> Dict[str, tuple[float, int, bool]]:
        snap: Dict[str, tuple[float, int, bool]] = {}
        count = 0
        for dirpath, dirnames, filenames in os.walk(root):
            for d in dirnames:
                full = os.path.join(dirpath, d)
                try:
                    st = os.stat(full)
                    snap[full] = (float(st.st_mtime), 0, True)
                except OSError:
                    pass
                count += 1
                if count >= max_items:
                    return snap
            for f in filenames:
                full = os.path.join(dirpath, f)
                try:
                    st = os.stat(full)
                    snap[full] = (float(st.st_mtime), int(st.st_size), False)
                except OSError:
                    pass
                count += 1
                if count >= max_items:
                    return snap
        return snap

    def _build_watchdog_handler(self) -> Any:
        monitor = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event: Any) -> None:
                ev_type = "New Folder" if event.is_directory else "Created"
                monitor.record_event(ev_type, event.src_path, is_dir=event.is_directory)

            def on_modified(self, event: Any) -> None:
                if not event.is_directory:
                    monitor.record_event("Modified", event.src_path, is_dir=False)

            def on_moved(self, event: Any) -> None:
                monitor.record_event(
                    "Renamed",
                    event.src_path,
                    dest_path=getattr(event, "dest_path", ""),
                    is_dir=event.is_directory,
                )

            def on_deleted(self, event: Any) -> None:
                monitor.record_event("Deleted", event.src_path, is_dir=event.is_directory)

        return _Handler()
