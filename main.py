"""
NEXUS FILES — Entry Point
Advanced Windows File Explorer, Search Engine, Disk Analyzer & File Management Suite.
100% Local • Fully Offline • Zero AI • Zero Cloud
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import tempfile
from pathlib import Path

from config.settings import SettingsManager
from database.database import LocalDatabase
from ui.main_window import NexusMainWindow, get_resource_path
from ui.qt_compat import PYSIDE6_AVAILABLE, QApplication, QIcon


def run_self_verification() -> int:
    """
    Execute a live smoke verification of the application shell, database initialization,
    and all 12 modules against a temporary workspace directory.
    """
    print("[NEXUS FILES] Starting application smoke verification...")
    with tempfile.TemporaryDirectory(prefix="nexus_verify_") as tmp:
        tmp_path = Path(tmp)
        cfg_file = tmp_path / "settings.json"
        db_file = tmp_path / "index.sqlite3"
        sample_dir = tmp_path / "workspace"
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "notes.txt").write_text("Nexus Files verification text", encoding="utf-8")
        (sample_dir / "requirements.txt").write_text("PySide6>=6.6.0\n", encoding="utf-8")

        settings_mgr = SettingsManager(cfg_file)
        settings_mgr.settings.default_drive = str(sample_dir)
        settings_mgr.settings.database_location = str(db_file)
        settings_mgr.settings.excluded_directories = []
        settings_mgr.save()

        db = LocalDatabase(db_file, enabled=True)
        app = QApplication(sys.argv)
        app.setApplicationName("NEXUS FILES")
        app.setOrganizationName("NexusDesktop")

        window = NexusMainWindow(settings_mgr=settings_mgr, db=db)
        window.show()

        # Verify all 12 pages are registered and navigable
        assert window.stack.count() == 12, f"Expected 12 pages, got {window.stack.count()}"
        for idx in range(12):
            window.sidebar.select_page(idx)
            assert window.stack.currentIndex() == idx

        # Trigger live synchronous operations on sample workspace
        res = window.page_analyzer.run_analysis(synchronous=True)
        assert res is not None and res.total_files >= 2
        window.page_dashboard.apply_analysis_result(res)

        search_hits = window.page_search.run_search(synchronous=True)
        assert len(search_hits) >= 2

        projects = window.page_projects.scan_projects()
        assert len(projects) == 1 and "Python" in projects[0].project_type

        insp = window.page_inspector.inspect_file(str(sample_dir / "notes.txt"))
        assert insp is not None and "Nexus Files" in insp.preview_text

        print(f"[NEXUS FILES] All 12 modules and core engines verified (PySide6 native={PYSIDE6_AVAILABLE}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NEXUS FILES — Windows File Explorer, Search Engine & Disk Analyzer"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run non-interactive self-test verification of all modules and exit.",
    )
    args = parser.parse_args()

    if args.verify:
        return run_self_verification()

    if not PYSIDE6_AVAILABLE:
        print(
            "PySide6 is required to display the interactive GUI window.\n"
            "Install dependencies via: pip install -r requirements.txt\n"
            "Running self-verification mode instead..."
        )
        return run_self_verification()

    if sys.platform == "win32" and not getattr(sys, "frozen", False):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NexusDesktop.NexusFiles.1")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("NEXUS FILES")
    app.setOrganizationName("NexusDesktop")
    icon_path = get_resource_path("resources/icons/nexus_app_icon.ico")
    if not icon_path.exists():
        icon_path = get_resource_path("resources/icons/nexus_files.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    settings_mgr = SettingsManager()
    db = LocalDatabase(
        settings_mgr.settings.database_location,
        enabled=settings_mgr.settings.database_enabled,
    )
    window = NexusMainWindow(settings_mgr=settings_mgr, db=db)
    show_maximized = False
    if hasattr(QApplication, "primaryScreen"):
        scr = QApplication.primaryScreen()
        if scr is not None:
            avail = scr.availableGeometry()
            if avail.width() <= 1440 or avail.height() <= 820:
                show_maximized = True
    if show_maximized and hasattr(window, "showMaximized"):
        window.showMaximized()
    else:
        window.show()
    if hasattr(window, "raise_"):
        window.raise_()
    if hasattr(window, "activateWindow"):
        window.activateWindow()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
