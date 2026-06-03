from __future__ import annotations

import shutil
from pathlib import Path


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    targets = [
        root / "__pycache__",
        root / ".pytest_cache",
        root / ".ruff_cache",
        root / "frontend" / ".next",
        root / "_local" / "cache",
        root / "_local" / "temp",
        root / "_local" / "reports",
    ]
    for target in targets:
        _remove(target)
        print(f"removed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
