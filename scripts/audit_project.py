from __future__ import annotations

from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    checks = {
        "backend_exists": root.joinpath("backend").is_dir(),
        "frontend_exists": root.joinpath("frontend").is_dir(),
        "_local_exists": root.joinpath("_local").is_dir(),
        "legacy_agents_still_present": root.joinpath("agents").is_dir(),
        "tests_physically_split": root.joinpath("tests", "backend").is_dir(),
        "sample_data_migrated": root.joinpath("data", "samples", "knowledge", "sample.md").is_file(),
    }
    for key, value in checks.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
