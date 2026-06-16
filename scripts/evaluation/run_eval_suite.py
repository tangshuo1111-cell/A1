from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluation.render_eval_overview import render_regression_overview  # noqa: E402
from tests.evaluation.runners.eval_complex_agent_runner import v3_case_file  # noqa: E402
from tests.evaluation.runners.eval_http_client import (  # noqa: E402
    BackendUnavailableError,
    EvalHttpClient,
)
from tests.evaluation.runners.eval_multiturn_runner import (  # noqa: E402
    run_multiturn_suite,
    v2_5_case_file,
)
from tests.evaluation.runners.eval_real_external_runner import (  # noqa: E402
    run_real_external_smoke_suite,
)
from tests.evaluation.runners.eval_runner import (  # noqa: E402
    run_suite,
    v1_case_file,
    v2_suite_case_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run evaluation suite")
    parser.add_argument(
        "--suite",
        required=True,
        choices=[
            "v1_route_exit_state",
            "v2_capability_web",
            "v2_capability_document",
            "v2_capability_video",
            "v2_capability_kb",
            "v2_capability_all",
            "v2_5_multiturn_state",
            "v3_complex_agent",
            "regression_all",
            "real_external_smoke",
        ],
    )
    args = parser.parse_args()

    client = EvalHttpClient()
    health_error: str | None = None
    if args.suite == "real_external_smoke":
        result = run_real_external_smoke_suite(client=client)
        print("suite: real_external_smoke")
        print(f"backend: {result['backend_base_url']}")
        print(f"final_verdict: {result['final_verdict']}")
        print(f"exit_code: {result['exit_code']}")
        print(f"json report: {result['report_paths']['json']}")
        print(f"markdown report: {result['report_paths']['markdown']}")
        return int(result["exit_code"])

    try:
        client.health_check()
    except BackendUnavailableError as exc:
        health_error = str(exc)
        if args.suite != "regression_all":
            print(health_error)
            return 1

    if args.suite == "regression_all":
        suite_defs = [
            ("v1_route_exit_state", v1_case_file()),
            ("v2_capability_all", None),
            ("v2_5_multiturn_state", v2_5_case_file()),
            ("v3_complex_agent", v3_case_file()),
        ]
        regression_results = []
        if health_error is not None:
            for suite_name, _case_file in suite_defs:
                regression_results.append(
                    {
                        "suite_name": suite_name,
                        "backend_unavailable": True,
                        "report_paths": {},
                        "total_cases": 0,
                        "passed_cases": 0,
                        "failed_cases": 0,
                        "pass_rate": 0.0,
                    }
                )
            overview_paths = render_regression_overview(
                regression_results=regression_results,
                backend_status="backend_unavailable",
                generated_at=Path().cwd().resolve().joinpath("").as_posix() and __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            )
            print(health_error)
            print("suite: regression_all")
            print(f"json report: {overview_paths['json']}")
            print(f"markdown report: {overview_paths['markdown']}")
            return 1

        for suite_name, case_file in suite_defs:
            if suite_name == "v2_5_multiturn_state":
                result = run_multiturn_suite(suite_name=suite_name, case_file=case_file, client=client)
                regression_results.append(
                    {
                        "suite_name": suite_name,
                        "report_paths": result["report_paths"],
                        "total_flows": len(result["flow_results"]),
                        "passed_flows": sum(1 for flow in result["flow_results"] if flow["passed"]),
                        "failed_flows": sum(1 for flow in result["flow_results"] if not flow["passed"]),
                        "pass_rate": round((sum(1 for flow in result["flow_results"] if flow["passed"]) / len(result["flow_results"])) * 100, 2) if result["flow_results"] else 0.0,
                        "flow_results": result["flow_results"],
                    }
                )
            else:
                result = run_suite(suite_name=suite_name, case_file=case_file, client=client)
                regression_results.append(
                    {
                        "suite_name": suite_name,
                        "report_paths": result["report_paths"],
                        "total_cases": len(result["case_results"]),
                        "passed_cases": sum(1 for case in result["case_results"] if case["passed"]),
                        "failed_cases": sum(1 for case in result["case_results"] if not case["passed"]),
                        "pass_rate": round((sum(1 for case in result["case_results"] if case["passed"]) / len(result["case_results"])) * 100, 2) if result["case_results"] else 0.0,
                        "case_results": result["case_results"],
                    }
                )
        overview_paths = render_regression_overview(
            regression_results=regression_results,
            backend_status="ok",
            generated_at=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
        )
        print("suite: regression_all")
        print(f"backend: {client.base_url}")
        print(f"json report: {overview_paths['json']}")
        print(f"markdown report: {overview_paths['markdown']}")
        return 0

    if args.suite == "v2_5_multiturn_state":
        result = run_multiturn_suite(suite_name=args.suite, case_file=v2_5_case_file(), client=client)
        passed = sum(1 for flow in result["flow_results"] if flow["passed"])
        total = len(result["flow_results"])
    else:
        case_file = v1_case_file() if args.suite == "v1_route_exit_state" else v2_suite_case_files().get(args.suite)
        if args.suite == "v3_complex_agent":
            case_file = v3_case_file()
        result = run_suite(suite_name=args.suite, case_file=case_file, client=client)
        passed = sum(1 for case in result["case_results"] if case["passed"])
        total = len(result["case_results"])
    print(f"suite: {args.suite}")
    print(f"backend: {result['backend_base_url']}")
    print(f"passed: {passed}/{total}")
    print(f"json report: {result['report_paths']['json']}")
    print(f"markdown report: {result['report_paths']['markdown']}")
    return 0 if passed == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
