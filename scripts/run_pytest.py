from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from python_runtime import PROJECT_ROOT, build_test_env, resolve_python_bin
from utf8_console import configure_utf8_stdio

configure_utf8_stdio()


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    python_bin = resolve_python_bin()
    cmd = [str(python_bin), "-m", "pytest", *args]
    return subprocess.run(cmd, cwd=PROJECT_ROOT, env=build_test_env()).returncode


if __name__ == "__main__":
    raise SystemExit(main())
