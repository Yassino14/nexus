"""
SQLite database schema and FTS5 virtual table definitions for NEXUS FILES.
"""

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_path TEXT NOT NULL,
    status TEXT NOT NULL, -- 'running', 'completed', 'interrupted', 'cancelled'
    started_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    files_indexed INTEGER DEFAULT 0,
    folders_indexed INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    last_directory TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    parent_dir TEXT NOT NULL,
    drive TEXT NOT NULL,
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL,
    extension TEXT NOT NULL,
    category TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    mtime REAL NOT NULL DEFAULT 0,
    ctime REAL NOT NULL DEFAULT 0,
    atime REAL NOT NULL DEFAULT 0,
    is_dir INTEGER NOT NULL DEFAULT 0,
    is_hidden INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT DEFAULT NULL,
    content_snippet TEXT DEFAULT NULL,
    indexed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_name_lower ON files(name_lower);
CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime);
CREATE INDEX IF NOT EXISTS idx_files_parent_dir ON files(parent_dir);
CREATE INDEX IF NOT EXISTS idx_files_drive ON files(drive);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256) WHERE sha256 IS NOT NULL;
"""

CREATE_FTS5_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    path UNINDEXED,
    name,
    extension,
    parent_dir,
    content_snippet,
    tokenize='unicode61 remove_diacritics 1'
);
"""
