from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.evaluation.runners.eval_case_loader import (  # noqa: E402
    default_case_file,
    load_eval_cases,
)


def main() -> int:
    case_path = default_case_file()
    cases = load_eval_cases(case_path)
    print(f"eval smoke file: {case_path}")
    print(f"case count: {len(cases)}")
    print("case ids:")
    for case in cases:
        print(f"- {case['case_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
