"""
Automated Tests for Optional SQLite Database, Corruption Recovery,
Incremental Indexing, and Universal Search Engine (Indexed & Direct Modes).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config.settings import SettingsManager
from core.search_engine import SearchEngine, SearchQuery
from database.database import LocalDatabase
from database.index_manager import IndexManager


class TestDatabaseAndSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="nexus_test_db_")
        self.root = Path(self.tmp_dir.name)
        self.settings_mgr = SettingsManager(self.root / "settings.json")
        self.settings_mgr.settings.excluded_directories = []
        self.settings_mgr.settings.content_indexing_enabled = True
        self.settings_mgr.save()

        self.data_dir = self.root / "files"
        (self.data_dir / "sub").mkdir(parents=True)
        (self.data_dir / "alpha_report.pdf").write_bytes(b"%PDF-1.4 " * 100)
        (self.data_dir / "beta_code.py").write_text("def compute_nexus_metric(): pass\n", encoding="utf-8")
        (self.data_dir / "sub" / "gamma_archive.zip").write_bytes(b"PK" * 2000)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_sqlite_indexing_incremental_and_corruption_recovery(self) -> None:
        db_file = self.root / "index.sqlite3"
        db = LocalDatabase(db_file, enabled=True)
        self.assertTrue(db.is_available)
        self.assertTrue(db.check_integrity())

        idx_mgr = IndexManager(db, self.settings_mgr)
        res1 = idx_mgr.index_directory(self.data_dir, incremental=False)
        self.assertEqual(res1["status"], "completed")
        self.assertEqual(res1["files_indexed"], 3)

        stats = idx_mgr.get_index_stats()
        self.assertEqual(stats["files_count"], 3)

        # Delete a file and run incremental index to verify stale entry pruning
        (self.data_dir / "sub" / "gamma_archive.zip").unlink()
        res2 = idx_mgr.index_directory(self.data_dir, incremental=True)
        self.assertEqual(res2["files_indexed"], 2)
        self.assertEqual(idx_mgr.get_index_stats()["files_count"], 2)

        # Simulate corrupted database file and verify automatic recovery
        db_file.write_bytes(b"CORRUPTED_SQLITE_HEADER_GARBAGE_BYTES")
        self.assertFalse(db.check_integrity())
        self.assertTrue(db.initialize())
        self.assertTrue(db.is_available)

    def test_universal_search_indexed_and_direct_modes_plus_fallback(self) -> None:
        db_file = self.root / "search_index.sqlite3"
        db = LocalDatabase(db_file, enabled=True)
        idx_mgr = IndexManager(db, self.settings_mgr)
        idx_mgr.index_directory(self.data_dir, incremental=False)

        engine = SearchEngine(db, self.settings_mgr)

        # 1. Mode A: Indexed search by partial name
        q_idx = SearchQuery(text="alpha", search_mode="Indexed", roots=[str(self.data_dir)])
        hits_idx = engine.search(q_idx)
        self.assertEqual(len(hits_idx), 1)
        self.assertEqual(hits_idx[0].name, "alpha_report.pdf")

        # 2. Mode B: Direct search by category filter
        q_dir = SearchQuery(category="Programming", search_mode="Direct", roots=[str(self.data_dir)])
        hits_dir = engine.search(q_dir)
        self.assertEqual(len(hits_dir), 1)
        self.assertEqual(hits_dir[0].name, "beta_code.py")

        # 3. Content search
        q_content = SearchQuery(
            content_query="compute_nexus_metric",
            search_mode="Direct",
            roots=[str(self.data_dir)],
        )
        hits_content = engine.search(q_content)
        self.assertEqual(len(hits_content), 1)
        self.assertEqual(hits_content[0].name, "beta_code.py")

        # 4. Fuzzy filename matching
        q_fuzzy = SearchQuery(
            text="alprpt",
            fuzzy_match=True,
            search_mode="Direct",
            roots=[str(self.data_dir)],
        )
        hits_fuzzy = engine.search(q_fuzzy)
        self.assertTrue(any(h.name == "alpha_report.pdf" for h in hits_fuzzy))

        # 5. Database disabled fallback: Indexed mode transparently falls back to Direct mode
        db.enabled = False
        q_fallback = SearchQuery(text="beta", search_mode="Indexed", roots=[str(self.data_dir)])
        hits_fb = engine.search(q_fallback)
        self.assertEqual(len(hits_fb), 1)
        self.assertEqual(hits_fb[0].name, "beta_code.py")

        # 6. Indexed root scoping must not leak into sibling directories sharing a prefix
        sibling_dir = self.root / "files_sibling"
        sibling_dir.mkdir(exist_ok=True)
        (sibling_dir / "alpha_sibling.txt").write_text("sibling", encoding="utf-8")
        db.enabled = True
        idx_mgr.index_directory(sibling_dir, incremental=False)
        hits_scoped = engine.search(SearchQuery(text="alpha", search_mode="Indexed", roots=[str(self.data_dir)]))
        self.assertEqual([h.name for h in hits_scoped], ["alpha_report.pdf"])
