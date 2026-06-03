from __future__ import annotations

import fnmatch
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

# Project root: 项目代码/
ROOT = Path(__file__).resolve().parent.parent

OUTPUT_REL = Path("_local") / "exports" / "project_analysis_clean.zip"

# Directory name fragments: exclude if any path segment equals these.
_EXCLUDE_DIR_PARTS = frozenset({
    "_local",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "htmlcov",
    "uploads",
    "logs",
    ".git",
})

_TOP_FILES = [
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    "requirements.lock",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore",
    ".gitignore",
    ".env.example",
]

# Explicit frontend files (also covered by frontend/ walk; listed for clarity / future checks).
_FRONTEND_EXPLICIT = [
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
]

_WALK_ROOTS = ("backend", "frontend", "tests", "scripts", Path("docs") / "current", Path("data") / "samples")


def _should_exclude(rel: Path) -> bool:
    """True if this relative path must not appear in the zip."""
    parts = rel.parts
    name = rel.name

    if any(p in _EXCLUDE_DIR_PARTS for p in parts):
        return True

    if len(parts) >= 2 and parts[0] == "data" and parts[1] == "cookies":
        return True

    if name == ".env" or name == ".env.local":
        return True

    lower = name.lower()
    suf = rel.suffix.lower()
    if suf in {".sqlite", ".sqlite3", ".db"} or lower == ".coverage":
        return True
    if lower.endswith((".sqlite-wal", ".sqlite-shm", ".sqlite-journal")):
        return True
    if name == "coverage.xml":
        return True
    if lower.endswith(".log"):
        return True

    return any(fnmatch.fnmatch(name, p) for p in ("*_cookies.txt",))


def _iter_files_under(sub: Path) -> list[Path]:
    if not sub.exists():
        return []
    out: list[Path] = []
    for path in sub.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if _should_exclude(rel):
            continue
        out.append(path)
    return sorted(out)


def _collect_paths() -> list[Path]:
    files: list[Path] = []

    for name in _TOP_FILES:
        p = ROOT / name
        if p.is_file():
            rel = p.relative_to(ROOT)
            if not _should_exclude(rel):
                files.append(p)

    readme = ROOT / "data" / "README.md"
    if readme.is_file():
        rel = readme.relative_to(ROOT)
        if not _should_exclude(rel):
            files.append(readme)

    for rel_str in _FRONTEND_EXPLICIT:
        p = ROOT / rel_str
        if p.is_file():
            rel = p.relative_to(ROOT)
            if not _should_exclude(rel):
                files.append(p)

    for pattern in ROOT.glob("frontend/next.config.*"):
        if pattern.is_file():
            rel = pattern.relative_to(ROOT)
            if not _should_exclude(rel):
                files.append(pattern)

    for sub in _WALK_ROOTS:
        sub_path = ROOT / sub if isinstance(sub, str) else ROOT / sub
        files.extend(_iter_files_under(sub_path))

    # De-duplicate (same file from walk + explicit list).
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in sorted(files, key=lambda x: x.relative_to(ROOT).as_posix()):
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        unique.append(p)
    return unique


def main() -> int:
    out_path = ROOT / OUTPUT_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    paths = _collect_paths()
    with ZipFile(out_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in paths:
            arc = path.relative_to(ROOT)
            zf.write(path, arcname=arc.as_posix())

    print(out_path.resolve())
    print(len(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
