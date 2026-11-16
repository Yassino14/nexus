"""
Programming Project Discovery Engine for NEXUS FILES.
Detects Python, JavaScript/TypeScript, Java, .NET/C#, Rust, Go, and Git repositories
across C: and D: while avoiding duplicate reporting of nested subdirectories
(e.g., node_modules, .venv, target, bin, obj).
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from config.settings import SettingsManager


@dataclass
class DetectedProject:
    """Metadata for a discovered software development project."""

    name: str
    project_type: str
    location: str
    last_modified: float
    config_files: List[str] = field(default_factory=list)
    git_branch: Optional[str] = None
    has_git: bool = False


class ProjectDetector:
    """Scans drives to identify software projects without descending into nested build/vendor dirs."""

    SKIP_DIRS: Set[str] = {
        "node_modules", ".git", ".hg", ".svn", "__pycache__", ".venv", "venv",
        "env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", "target",
        "bin", "obj", ".vs", ".idea", ".next", ".nuxt", "vendor", "_internal",
        "AppData", "ProgramData", "Windows", "Program Files", "Program Files (x86)",
        "$Recycle.Bin", "System Volume Information", "msys64", "oracle11g",
        "OracleXE112_Win64", "Visual Studio", "Microsoft VS Code", "xampp",
    }

    PYTHON_MARKERS = {"requirements.txt", "pyproject.toml", "manage.py", "app.py", "setup.py", "Pipfile"}
    JS_MARKERS = {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "tsconfig.json"}
    JAVA_MARKERS = {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"}
    RUST_MARKERS = {"Cargo.toml"}
    GO_MARKERS = {"go.mod"}

    def __init__(self, settings_mgr: Optional[SettingsManager] = None) -> None:
        self.settings_mgr = settings_mgr or SettingsManager()

    def scan_for_projects(
        self,
        roots: List[str | Path],
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> List[DetectedProject]:
        """Discover programming projects across `roots` and prevent nested duplicate reports."""
        projects: List[DetectedProject] = []
        seen_locations: Set[str] = set()

        for root in roots:
            root_str = os.path.abspath(str(root))
            if not os.path.exists(root_str):
                continue
            self._walk_projects(root_str, projects, seen_locations, cancel_check)

        projects.sort(key=lambda p: p.last_modified, reverse=True)
        return projects

    def _walk_projects(
        self,
        root_dir: str,
        projects: List[DetectedProject],
        seen_locations: Set[str],
        cancel_check: Optional[Callable[[], bool]],
    ) -> None:
        queue: deque[str] = deque([root_dir])
        while queue:
            if cancel_check and cancel_check():
                return
            current_dir = queue.popleft()
            if self.settings_mgr.is_path_excluded(current_dir):
                continue

            try:
                entries = list(os.scandir(current_dir))
            except OSError:
                continue

            file_names = {e.name for e in entries if e.is_file(follow_symlinks=False)}
            dir_names = {e.name for e in entries if e.is_dir(follow_symlinks=False)}

            detected_types: List[str] = []
            matched_configs: List[str] = []

            py_hits = sorted(file_names & self.PYTHON_MARKERS)
            if py_hits:
                detected_types.append("Python")
                matched_configs.extend(py_hits)

            js_hits = sorted(file_names & self.JS_MARKERS)
            if js_hits:
                detected_types.append("JavaScript / Node.js")
                matched_configs.extend(js_hits)

            java_hits = sorted(file_names & self.JAVA_MARKERS)
            if java_hits:
                detected_types.append("Java")
                matched_configs.extend(java_hits)

            dotnet_hits = sorted(
                f for f in file_names if f.endswith(".sln") or f.endswith(".csproj") or f.endswith(".fsproj")
            )
            if dotnet_hits:
                detected_types.append(".NET / C#")
                matched_configs.extend(dotnet_hits)

            rust_hits = sorted(file_names & self.RUST_MARKERS)
            if rust_hits:
                detected_types.append("Rust")
                matched_configs.extend(rust_hits)

            go_hits = sorted(file_names & self.GO_MARKERS)
            if go_hits:
                detected_types.append("Go")
                matched_configs.extend(go_hits)

            has_git = ".git" in dir_names
            if has_git and not detected_types:
                detected_types.append("Git Repository")
                matched_configs.append(".git")

            if detected_types:
                norm_loc = os.path.normcase(current_dir)
                if norm_loc not in seen_locations:
                    seen_locations.add(norm_loc)
                    git_branch = self._read_git_branch(current_dir) if has_git else None
                    try:
                        mtime = os.path.getmtime(current_dir)
                    except OSError:
                        mtime = 0.0
                    projects.append(
                        DetectedProject(
                            name=os.path.basename(current_dir) or current_dir,
                            project_type=" + ".join(detected_types),
                            location=current_dir,
                            last_modified=mtime,
                            config_files=matched_configs,
                            git_branch=git_branch,
                            has_git=has_git,
                        )
                    )
                # Do not descend into subdirectories of a discovered project to avoid reporting nested sub-packages
                continue

            for e in entries:
                try:
                    is_junc = e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction())
                    if not is_junc and e.is_dir(follow_symlinks=False) and e.name not in self.SKIP_DIRS and not e.name.startswith("."):
                        queue.append(e.path)
                except OSError:
                    continue

    @staticmethod
    def _read_git_branch(project_dir: str) -> Optional[str]:
        head_file = Path(project_dir) / ".git" / "HEAD"
        try:
            if head_file.exists():
                raw = head_file.read_text(encoding="utf-8", errors="ignore").strip()
                if raw.startswith("ref: refs/heads/"):
                    return raw.replace("ref: refs/heads/", "")
                return raw[:12]
        except Exception:
            pass
        return None
