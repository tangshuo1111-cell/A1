from __future__ import annotations

from python_runtime import collect_runtime_report
from utf8_console import configure_utf8_stdio

configure_utf8_stdio()


def main() -> int:
    report = collect_runtime_report()
    print(f"selected_python={report['selected_python']}")
    print(f"LIGHT_MAQA_PYTHON={report['light_maqa_python'] or 'EMPTY'}")
    print(f"PATH python={report['path_python'] or 'EMPTY'}")
    print(f"PATH py={report['path_py'] or 'EMPTY'}")
    print("candidates:")
    for row in report["candidates"]:
        version = row["version"]
        version_text = ".".join(str(part) for part in version) if version else "unknown"
        tags = []
        if row["selected"]:
            tags.append("selected")
        if row["supported"]:
            tags.append("supported")
        else:
            tags.append("unsupported")
        if not row["exists"]:
            tags.append("missing")
        print(f"  - {row['path']} | version={version_text} | {', '.join(tags)}")
    warnings = report["warnings"]
    if warnings:
        print("warnings:")
        for item in warnings:
            print(f"  - {item}")
    else:
        print("warnings: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
