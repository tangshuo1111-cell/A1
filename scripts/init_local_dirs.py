from __future__ import annotations

from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    local_root = root / "_local"
    subdirs = ("data", "cache", "logs", "temp", "uploads", "outputs", "reports")
    for name in subdirs:
        (local_root / name).mkdir(parents=True, exist_ok=True)
    print(f"initialized _local directories under {local_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
