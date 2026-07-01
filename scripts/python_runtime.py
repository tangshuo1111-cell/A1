from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from shutil import which

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

PROJECT_ROOT = SCRIPT_ROOT.parent
MIN_VERSION = (3, 11)
PREFERRED_CANDIDATES = (
    Path(r"D:\软件\Python312\python.exe"),
    Path(sys.executable),
)


def _version_tuple(python_bin: Path) -> tuple[int, int, int] | None:
    try:
        proc = subprocess.run(
            [str(python_bin), "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    try:
        major, minor, patch = [int(part) for part in raw.split(".")[:3]]
    except (TypeError, ValueError):
        return None
    return (major, minor, patch)


def _is_supported(version: tuple[int, int, int] | None) -> bool:
    if version is None:
        return False
    return version[:2] >= MIN_VERSION


def resolve_python_bin() -> Path:
    env_python = os.environ.get("LIGHT_MAQA_PYTHON")
    candidates = []
    if env_python:
        candidates.append(Path(env_python))
    candidates.extend(PREFERRED_CANDIDATES)
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if not candidate.exists():
            continue
        version = _version_tuple(candidate)
        if _is_supported(version):
            return candidate
    raise RuntimeError(
        "No supported Python runtime found. "
        "Set LIGHT_MAQA_PYTHON or install an accessible Python >= 3.11."
    )


def collect_runtime_report() -> dict[str, object]:
    env_python = os.environ.get("LIGHT_MAQA_PYTHON")
    path_python = which("python")
    path_py = which("py")
    ordered_candidates: list[Path] = []
    seen: set[str] = set()

    def push(candidate: str | Path | None) -> None:
        if not candidate:
            return
        path = Path(candidate)
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        ordered_candidates.append(path)

    push(env_python)
    for candidate in PREFERRED_CANDIDATES:
        push(candidate)
    push(path_python)

    candidate_rows: list[dict[str, object]] = []
    for candidate in ordered_candidates:
        exists = candidate.exists()
        version = _version_tuple(candidate) if exists else None
        candidate_rows.append(
            {
                "path": str(candidate),
                "exists": exists,
                "version": version,
                "supported": _is_supported(version),
                "selected": False,
            }
        )

    selected = resolve_python_bin()
    for row in candidate_rows:
        if row["path"].lower() == str(selected).lower():
            row["selected"] = True

    warnings: list[str] = []
    supported_rows = [row for row in candidate_rows if row["supported"]]
    if len(supported_rows) > 1:
        warnings.append("Detected multiple supported Python runtimes; keep using the unified script entrypoints.")
    if path_python and Path(path_python).resolve() != selected.resolve():
        warnings.append("PATH python does not match the selected project runtime.")
    if env_python and Path(env_python).resolve() != selected.resolve():
        warnings.append("LIGHT_MAQA_PYTHON is set but does not resolve to the selected runtime.")
    if path_py:
        warnings.append("Legacy 'py' launcher is present; avoid it in project commands to keep runtime selection stable.")

    return {
        "selected_python": str(selected),
        "light_maqa_python": env_python or "",
        "path_python": path_python or "",
        "path_py": path_py or "",
        "candidates": candidate_rows,
        "warnings": warnings,
    }


def build_test_env() -> dict[str, str]:
    env = dict(os.environ)
    backend_root = str(PROJECT_ROOT / "backend")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = backend_root if not existing else f"{backend_root}{os.pathsep}{existing}"
    return env
