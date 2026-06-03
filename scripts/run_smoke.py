from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, "-m", "pytest", "-q", "-m", "smoke"]
    return subprocess.run(cmd, cwd=root).returncode


if __name__ == "__main__":
    raise SystemExit(main())
