r"""
Automated Tests for Filesystem Safety Rules & File Operations:
- Create folder / file
- Copy / Move / Rename
- Recursive copy protection (blocking copying folder into its own subfolder)
- Protected Windows system path blocking (C:\Windows, C:\, etc.)
- Safe Recycle Bin deletion and one-click Undo restoration
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config.settings import SettingsManager
from core.file_operations import FileOperationsManager


class TestOperationsAndSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="nexus_test_ops_")
        self.root = Path(self.tmp_dir.name)
        self.settings_mgr = SettingsManager(self.root / "settings.json")
        self.ops = FileOperationsManager(self.settings_mgr)
        self.ops.recycle_fallback_dir = self.root / ".recycle_staging"

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_system_path_protection(self) -> None:
        self.assertTrue(self.settings_mgr.is_system_protected_path("C:\\"))
        self.assertTrue(self.settings_mgr.is_system_protected_path("D:\\"))
        self.assertTrue(self.settings_mgr.is_system_protected_path("/"))
        ok, msg = self.ops.delete_to_recycle_bin("/")
        self.assertFalse(ok)
        self.assertIn("Safety block", msg)

    def test_prevent_recursive_copy_and_move(self) -> None:
        parent = self.root / "ProjectFolder"
        child = parent / "SubFolder"
        child.mkdir(parents=True)
        (parent / "readme.md").write_text("hi", encoding="utf-8")

        ok_copy, msg_copy = self.ops.copy_item(parent, child)
        self.assertFalse(ok_copy)
        self.assertIn("Recursive copy blocked", msg_copy)

        ok_move, msg_move = self.ops.move_item(parent, child)
        self.assertFalse(ok_move)
        self.assertIn("Recursive move blocked", msg_move)

    def test_crud_recycle_and_undo_lifecycle(self) -> None:
        work = self.root / "workspace"
        work.mkdir()

        ok, folder_path = self.ops.create_folder(work, "Docs")
        self.assertTrue(ok)
        ok, file_path = self.ops.create_file(work, "draft.txt", "initial content")
        self.assertTrue(ok)

        # Rename file
        ok, renamed_path = self.ops.rename_item(file_path, "final.txt")
        self.assertTrue(ok)
        self.assertTrue(Path(renamed_path).exists())

        # Undo rename -> back to draft.txt
        ok, _ = self.ops.undo_last_operation()
        self.assertTrue(ok)
        self.assertTrue(Path(file_path).exists())

        # Move file into Docs
        ok, moved_path = self.ops.move_item(file_path, folder_path)
        self.assertTrue(ok)
        self.assertTrue(Path(moved_path).exists())

        # Undo move -> back to workspace/draft.txt
        ok, _ = self.ops.undo_last_operation()
        self.assertTrue(ok)
        self.assertTrue(Path(file_path).exists())

        # Delete to safe Recycle Bin
        ok, _ = self.ops.delete_to_recycle_bin(file_path)
        self.assertTrue(ok)
        self.assertFalse(Path(file_path).exists())
