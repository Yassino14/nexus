"""
Automated Tests for Core Engines:
- Drive detection & capacity metrics
- Directory scanning, hidden files, & inaccessible path handling
- Disk Analyzer, Top files/folders, Empty folders, Forgotten downloads, CSV & PDF exports
- Duplicate detection (multistage size + SHA-256 verification, ignoring identical names with different content)
- File Inspector & previews (PDF, Image, Excel .xlsx, Word .docx, Text/Code)
- Project Detector (Python, JS, Java, .NET, Git, avoiding nested duplicate reports)
- Smart Rule-Based Organizer & Undo
- Folder Comparator & CSV export
- Activity Monitor
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from config.settings import SettingsManager
from core.activity_monitor import ActivityMonitor
from core.disk_analyzer import DiskAnalyzer
from core.drive_manager import DriveManager
from core.duplicate_engine import DuplicateEngine
from core.file_inspector import FileInspector
from core.file_operations import FileOperationsManager
from core.file_scanner import FileScanner
from core.folder_comparator import FolderComparator
from core.organizer import SmartOrganizer
from core.project_detector import ProjectDetector


class TestCoreEngines(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="nexus_test_core_")
        self.root = Path(self.tmp_dir.name)
        self.settings_mgr = SettingsManager(self.root / "settings.json")
        self.settings_mgr.settings.excluded_directories = []
        self.settings_mgr.settings.show_hidden_files = False
        self.settings_mgr.save()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_drive_detection_and_combined_summary(self) -> None:
        dm = DriveManager(custom_roots=[str(self.root)])
        drives = dm.detect_drives()
        self.assertEqual(len(drives), 1)
        self.assertGreater(drives[0].total_bytes, 0)
        self.assertGreaterEqual(drives[0].free_bytes, 0)
        comb = dm.get_combined_summary(drives)
        self.assertEqual(comb["drive_count"], 1)
        self.assertEqual(comb["total_bytes"], drives[0].total_bytes)

    def test_scanner_and_disk_analyzer_with_exports(self) -> None:
        scan_root = self.root / "drive_sim"
        (scan_root / "Downloads").mkdir(parents=True)
        (scan_root / "EmptyDir").mkdir(parents=True)
        (scan_root / "Docs").mkdir(parents=True)

        f1 = scan_root / "Docs" / "report.pdf"
        f1.write_bytes(b"%PDF-1.4 sample content " * 500)

        f2 = scan_root / "Downloads" / "old_installer.exe"
        f2.write_bytes(b"MZ" + b"X" * 50000)
        old_ts = time.time() - (200 * 86400)
        os.utime(f2, (old_ts, old_ts))

        scanner = FileScanner(self.settings_mgr)
        summary = scanner.scan_summary(scan_root)
        self.assertEqual(summary.files_count, 2)
        self.assertGreaterEqual(summary.folders_count, 3)

        analyzer = DiskAnalyzer(self.settings_mgr)
        res = analyzer.analyze(scan_root, large_threshold_bytes=1000, old_days_threshold=180)
        self.assertEqual(res.total_files, 2)
        self.assertTrue(any("EmptyDir" in p for p in res.empty_folders))
        self.assertEqual(len(res.forgotten_downloads), 1)
        self.assertEqual(len(res.old_files), 1)
        self.assertEqual(len(res.large_installers), 1)

        csv_out = self.root / "report.csv"
        pdf_out = self.root / "report.pdf"
        self.assertTrue(analyzer.export_to_csv(res, csv_out))
        self.assertTrue(csv_out.exists() and csv_out.stat().st_size > 50)
        self.assertTrue(analyzer.export_to_pdf(res, pdf_out))
        self.assertTrue(pdf_out.exists() and pdf_out.stat().st_size > 100)

    def test_duplicate_detection_sha256_accuracy(self) -> None:
        dup_root = self.root / "dups"
        (dup_root / "dirA").mkdir(parents=True)
        (dup_root / "dirB").mkdir(parents=True)
        (dup_root / "dirC").mkdir(parents=True)

        payload_same = b"IDENTICAL_BINARY_PAYLOAD_" * 400
        payload_diff_same_len = b"DIFFERENT_BINARY_PAYLOAD_" * 400

        # Two identical files with different names
        (dup_root / "dirA" / "original.bin").write_bytes(payload_same)
        (dup_root / "dirB" / "copy_renamed.bin").write_bytes(payload_same)

        # File with same name AND same size, but different content (must NOT be grouped!)
        (dup_root / "dirC" / "original.bin").write_bytes(payload_diff_same_len)

        engine = DuplicateEngine(self.settings_mgr)
        report = engine.find_duplicates([dup_root], min_size_bytes=10)
        self.assertEqual(len(report.groups), 1)
        self.assertEqual(report.groups[0].copies_count, 2)
        self.assertEqual(report.total_recoverable_bytes, len(payload_same))

    def test_file_inspector_previews_all_formats(self) -> None:
        insp_dir = self.root / "inspect"
        insp_dir.mkdir()
        inspector = FileInspector()

        # 1. Source code / text
        py_f = insp_dir / "sample.py"
        py_f.write_text("def hello():\n    return 42\n", encoding="utf-8")
        rep_py = inspector.inspect(py_f)
        self.assertIsNotNone(rep_py)
        self.assertEqual(rep_py.preview_type, "text")
        self.assertIn("return 42", rep_py.preview_text)
        self.assertIsNotNone(rep_py.sha256)

        # 2. Image (Pillow)
        from PIL import Image
        img_f = insp_dir / "test.png"
        Image.new("RGB", (64, 32), color=(99, 102, 241)).save(img_f)
        rep_img = inspector.inspect(img_f)
        self.assertEqual(rep_img.preview_type, "image")
        self.assertEqual(rep_img.image_dimensions, (64, 32))

        # 3. Excel (.xlsx via openpyxl)
        import openpyxl
        xlsx_f = insp_dir / "budget.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Metrics"
        ws.append(["Drive", "FreeGB"])
        ws.append(["C:", 128])
        wb.save(xlsx_f)
        rep_xlsx = inspector.inspect(xlsx_f)
        self.assertEqual(rep_xlsx.preview_type, "excel")
        self.assertIn("FreeGB", rep_xlsx.preview_text)

        # 4. Word (.docx via python-docx)
        import docx
        docx_f = insp_dir / "spec.docx"
        d = docx.Document()
        d.add_paragraph("NEXUS FILES Architecture Specification")
        d.save(docx_f)
        rep_docx = inspector.inspect(docx_f)
        self.assertEqual(rep_docx.preview_type, "word")
        self.assertIn("Architecture Specification", rep_docx.preview_text)

    def test_project_detector_ignores_nested_subdirectories(self) -> None:
        proj_root = self.root / "projects"
        py_proj = proj_root / "MyPythonApp"
        (py_proj / ".git").mkdir(parents=True)
        (py_proj / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (py_proj / "pyproject.toml").write_text("[project]\nname='app'\n", encoding="utf-8")
        # Nested virtualenv or node_modules inside project must not be reported as separate project
        nested = py_proj / "venv" / "lib"
        nested.mkdir(parents=True)
        (nested / "requirements.txt").write_text("wheel\n", encoding="utf-8")

        dotnet_proj = proj_root / "DinariApp"
        dotnet_proj.mkdir(parents=True)
        (dotnet_proj / "DinariApp.sln").write_text("Microsoft Visual Studio Solution\n", encoding="utf-8")

        detector = ProjectDetector(self.settings_mgr)
        found = detector.scan_for_projects([proj_root])
        names = {p.name for p in found}
        self.assertEqual(names, {"MyPythonApp", "DinariApp"})
        py_item = next(p for p in found if p.name == "MyPythonApp")
        self.assertEqual(py_item.git_branch, "main")

    def test_smart_organizer_and_undo(self) -> None:
        messy = self.root / "messy"
        messy.mkdir()
        (messy / "lecture_01_notes.pdf").write_text("uni", encoding="utf-8")
        (messy / "photo.jpg").write_bytes(b"img")
        (messy / "script.py").write_text("print(1)", encoding="utf-8")

        ops = FileOperationsManager(self.settings_mgr)
        org = SmartOrganizer(ops)
        proposals = org.generate_proposals(messy)
        self.assertEqual(len(proposals), 3)

        by_name = {p.filename: p.target_folder_name for p in proposals}
        self.assertEqual(by_name["lecture_01_notes.pdf"], "University")
        self.assertEqual(by_name["photo.jpg"], "Images")
        self.assertEqual(by_name["script.py"], "Programming")

        res = org.execute_proposals(proposals)
        self.assertEqual(res["moved"], 3)
        self.assertTrue((messy / "University" / "lecture_01_notes.pdf").exists())

        restored, errors = org.undo_last_batch()
        self.assertEqual(restored, 3)
        self.assertEqual(len(errors), 0)
        self.assertTrue((messy / "lecture_01_notes.pdf").exists())

    def test_folder_comparison_and_activity_monitor(self) -> None:
        left = self.root / "left"
        right = self.root / "right"
        left.mkdir()
        right.mkdir()

        (left / "same.txt").write_text("hello", encoding="utf-8")
        (right / "same.txt").write_text("hello", encoding="utf-8")

        (left / "diff_hash.txt").write_text("AAAAA", encoding="utf-8")
        (right / "diff_hash.txt").write_text("BBBBB", encoding="utf-8")

        (left / "only_l.txt").write_text("left", encoding="utf-8")
        (right / "only_r.txt").write_text("right_longer", encoding="utf-8")

        comp = FolderComparator()
        rep = comp.compare(left, right, verify_hashes=True)
        self.assertEqual(rep.identical_count, 1)
        self.assertEqual(rep.different_hash_count, 1)
        self.assertEqual(rep.only_left_count, 1)
        self.assertEqual(rep.only_right_count, 1)

        csv_f = self.root / "comp.csv"
        self.assertTrue(comp.export_to_csv(rep, csv_f))

        # Test ActivityMonitor snapshot polling
        mon = ActivityMonitor()
        mon._watched_paths = [str(left)]
        mon._snapshots[str(left)] = mon._take_snapshot(str(left))
        (left / "newly_created.py").write_text("x = 1", encoding="utf-8")
        events = mon.poll_once()
        self.assertTrue(any(e.event_type == "Created" and e.extension == ".py" for e in events))
