from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.evaluation.runners.eval_sandbox import (  # noqa: E402
    clear_eval_sandbox_outputs,
    ensure_eval_sandbox_dirs,
    list_eval_sandbox_dirs,
)


def main() -> int:
    ensure_eval_sandbox_dirs()
    clear_eval_sandbox_outputs()
    print("eval sandbox directories:")
    for name, path in list_eval_sandbox_dirs().items():
        print(f"- {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
