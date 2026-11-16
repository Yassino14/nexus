"""
Automated Tests for UI Window, All 12 Pages, Interactive Treemap Drill-Down,
and Background Workers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config.settings import SettingsManager
from database.database import LocalDatabase
from ui.main_window import NexusMainWindow
from ui.qt_compat import QApplication


class TestUIAndWorkers(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="nexus_test_ui_")
        self.root = Path(self.tmp_dir.name)
        (self.root / "FolderA").mkdir()
        (self.root / "FolderB").mkdir()
        (self.root / "FolderA" / "data.bin").write_bytes(b"A" * 8192)
        (self.root / "FolderB" / "data_copy.bin").write_bytes(b"A" * 8192)

        self.settings_mgr = SettingsManager(self.root / "settings.json")
        self.settings_mgr.settings.default_drive = str(self.root)
        self.settings_mgr.settings.database_location = str(self.root / "ui_index.sqlite3")
        self.settings_mgr.settings.excluded_directories = []
        self.settings_mgr.save()

        self.db = LocalDatabase(self.settings_mgr.settings.database_location, enabled=True)
        self.app = QApplication.instance() or QApplication([])
        self.window = NexusMainWindow(self.settings_mgr, self.db)

    def tearDown(self) -> None:
        self.window.close()
        self.tmp_dir.cleanup()

    def test_all_12_pages_and_interactive_treemap_navigation(self) -> None:
        self.assertEqual(self.window.stack.count(), 12)

        # Disk Analyzer & Treemap drill-down
        res = self.window.page_analyzer.run_analysis(synchronous=True)
        self.assertIsNotNone(res)
        self.assertGreaterEqual(len(self.window.page_analyzer.treemap.computed_rects), 1)
        clicked_dir = self.window.page_analyzer.treemap.click_at_index(0)
        self.assertIsNotNone(clicked_dir)
        self.assertEqual(self.window.page_analyzer.current_treemap_root, clicked_dir)
        self.window.page_analyzer.treemap_navigate_up()
        self.assertEqual(self.window.page_analyzer.current_treemap_root, str(self.root))

        # Duplicate Finder UI
        dup_rep = self.window.page_duplicates.run_scan(synchronous=True)
        self.assertIsNotNone(dup_rep)
        self.assertEqual(len(dup_rep.groups), 1)
        selected_count = self.window.page_duplicates.select_all_but_one()
        self.assertEqual(selected_count, 1)

        # Large Files UI
        large_hits = self.window.page_large_files.scan_large_files(min_bytes_override=4096)
        self.assertEqual(len(large_hits), 2)

        # Explorer multi-tab & folder creation
        tab = self.window.page_explorer.active_tab()
        self.assertIsNotNone(tab)
        self.assertTrue(self.window.page_explorer.action_new_folder("CreatedFromUI"))
        self.assertTrue((self.root / "CreatedFromUI").exists())

        # Duplicate tree pruning & Settings reset synchronization
        removed = self.window.page_duplicates.delete_checked_duplicates()
        self.assertEqual(removed, 1)
        self.assertEqual(self.window.page_duplicates.tree.topLevelItemCount(), 0)

        self.window.page_settings.db_enabled_chk.setChecked(False)
        self.window.page_settings.reset_defaults()
        self.assertTrue(self.window.page_settings.db_enabled_chk.isChecked())
