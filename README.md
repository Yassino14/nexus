# NEXUS FILES

**Advanced Windows File Explorer, Search Engine, Disk Analyzer & File Management Suite**

NEXUS FILES is a 100% local, offline desktop application for Windows 10/11 that combines the capabilities of **Windows File Explorer**, **Everything Search**, **WizTree / WinDirStat**, **Duplicate Cleaner**, and **Rule-Based File Organization** inside one cohesive dark-mode interface inspired by Linear, Raycast, and Windows 11.

## Key Principles & Guarantees

- **100% Local & Offline**: Zero AI features, zero cloud sync, zero external APIs, zero telemetry.
- **Database-Optional Architecture**: Uses SQLite (WAL mode + FTS5) as an optional local search accelerator. Every feature—including Direct Search, File Explorer, Disk Analyzer, Duplicate Finder, and Smart Organizer—continues working seamlessly even if the SQLite index is disabled, missing, or deleted.
- **Strict Filesystem Safety**:
  - Normal deletions always route to the **Windows Recycle Bin** (`send2trash` / Win32 `SHFileOperationW` with `FOF_ALLOWUNDO`) or reversible staging.
  - Protects critical Windows system directories (`C:\\Windows`, `C:\\Program Files`, drive roots) against accidental modification or deletion.
  - Blocks recursive copy/move loops (destination inside source).
  - Verifies destination free disk space prior to copying.
  - Detects locked files and permission boundaries gracefully without crashing.
  - Logs all file operations and supports one-click **Undo**.

## 12 Integrated Modules

1. **Dashboard**: Real-time drive detection (`C:\\`, `D:\\`, and Combined view), capacity donut chart, category & extension breakdowns, file age distribution, and largest folders/files tables. Clearly labels `Estimated (OS Volume)`, `Scanned`, and `Indexed` statistics.
2. **File Explorer**: Multi-tab and Dual-Pane file commander with breadcrumb navigation, Back/Forward/Up history, Grid/List/Detailed views, hidden file toggle, keyboard shortcuts (`Ctrl+C`, `Ctrl+X`, `Ctrl+V`, `F2`, `Delete`, `Backspace`, `Ctrl+F`, `F5`), and Undo.
3. **Global Search**: Dual-mode search engine (**Mode A: Indexed SQLite FTS5** and **Mode B: Direct Filesystem Scan**) with fuzzy matching, content search, category filter pills, size/date filters, saved searches, and search history.
4. **Disk Analyzer**: Deep directory scanner with an **Interactive Treemap** (click any folder block to drill down), Top 100 largest files, Top 50 largest folders, empty folders, forgotten downloads, large archives/installers, and **CSV & PDF export**.
5. **Duplicate Finder**: 6-stage SHA-256 duplicate detector (Size grouping → Unique size pruning → 64 KB head/tail pre-hash → Full SHA-256 verification → Recoverable space calculation) with "Select All But One Copy".
6. **Large Files**: Quick filters (`> 100 MB`, `> 500 MB`, `> 1 GB`, `> 5 GB`, or custom MB) sorted largest-first.
7. **Smart Organizer**: Deterministic rule-based organizer sorting loose files into `Documents/`, `Images/`, `Videos/`, `Audio/`, `Archives/`, `Installers/`, `Programming/`, `University/`, and `Projects/` with dry-run preview and batch Undo.
8. **File Inspector**: Non-executing metadata & SHA-256 inspector with built-in previews for **PDF**, **Images**, **Excel (`.xlsx`)**, **Word (`.docx`)**, and **Source Code / Text**.
9. **Project Finder**: Discovers Python, JavaScript/Node.js, Java, .NET/C#, Rust, Go, and Git projects across `C:` and `D:` without reporting nested `node_modules` or `.venv` directories.
10. **Recent Activity**: Configurable, low-overhead filesystem monitor (`watchdog` + snapshot diff fallback) tracking Created, Modified, Renamed, and Deleted items.
11. **Folder Comparison**: Non-destructive recursive comparison between two folders highlighting items Only in First, Only in Second, Different Size, Different SHA-256 Hash, and Identical files, with CSV export.
12. **Settings**: Local JSON configuration for themes, accent colors, default drive, SQLite index location/maintenance (Verify Integrity, Rebuild, Clear), excluded paths, worker limits, and safety confirmations.

## Quick Start (Windows 10 / 11)

### Option 1: One-Click Run Script
Double-click `scripts\\run.bat` or run from Command Prompt / PowerShell:
```bat
scripts\\run.bat
```

### Option 2: Manual Virtual Environment Setup
```powershell
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python main.py
```

### Running Automated Tests
```powershell
python -m unittest discover -s tests -v
```

### Building Standalone Windows `.exe` (PyInstaller)
```bat
scripts\\build.bat
```
The packaged executable will be created at `dist\\NexusFiles\\NexusFiles.exe`.
