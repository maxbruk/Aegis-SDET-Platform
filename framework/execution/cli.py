"""AEGIS orchestration CLI wrapping pytest, environment validation, and reliability reports."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence

import httpx

from framework.config.settings import settings
from framework.execution.run_context import RunContext
from framework.telemetry.reliability import ReliabilityAnalyzer

SUITE_TO_MARKER: dict[str, str | None] = {
    "all": None,
    "unit": "unit",
    "api": "api",
    "ui_mocked": "ui_mocked",
    "integration": "integration",
    "e2e": "e2e",
    "concurrency": "concurrency",
    "resilience": "resilience",
    "performance": "performance",
    "visual": "visual",
    "a11y": "a11y",
    "smoke": "smoke",
}

BACKEND_REQUIRED_SUITES = {"integration", "e2e", "concurrency"}


def build_pytest_command(
    suite: str,
    workers: int,
    run_context: RunContext,
    extra_args: Sequence[str] = (),
) -> list[str]:
    """Build the subprocess pytest command line for a suite and run context."""
    cmd = [sys.executable, "-m", "pytest", "-v"]
    marker = SUITE_TO_MARKER.get(suite)
    if marker:
        cmd.extend(["-m", marker])
    if workers > 1:
        cmd.extend(["-n", str(workers)])
    cmd.extend(
        [
            f"--junitxml={run_context.run_dir / 'junit.xml'}",
            f"--alluredir={run_context.allure_results_dir}",
            f"--html={run_context.run_dir / 'report.html'}",
            "--self-contained-html",
        ]
    )
    cmd.extend(extra_args)
    return cmd


def check_backend_availability(api_url: str) -> bool:
    """Probe the SUT /health endpoint to verify backend readiness."""
    try:
        response = httpx.get(f"{api_url.rstrip('/')}/health", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _run_command(args: argparse.Namespace) -> int:
    run_id = args.run_id or RunContext.generate_run_id()
    run_ctx = RunContext(run_id=run_id)
    target_api_url = args.api_url or settings.API_URL

    cmd = build_pytest_command(
        suite=args.suite,
        workers=args.workers,
        run_context=run_ctx,
        extra_args=args.pytest_args,
    )

    env = os.environ.copy()
    env["AEGIS_RUN_ID"] = run_ctx.run_id
    env["BROWSER_NAME"] = args.browser
    env["ENVIRONMENT"] = args.environment
    if args.base_url:
        env["BASE_URL"] = args.base_url
    if args.api_url:
        env["API_URL"] = args.api_url
    if args.require_backend:
        env["REQUIRE_BACKEND"] = "true"

    print(f"[AEGIS] Run ID: {run_ctx.run_id}")
    print(f"[AEGIS] Suite: {args.suite} | Browser: {args.browser} | Env: {args.environment}")
    print(f"[AEGIS] Command: {' '.join(cmd)}")

    if args.dry_run:
        return 0

    if args.suite in BACKEND_REQUIRED_SUITES and not check_backend_availability(target_api_url):
        print(
            f"[AEGIS] Backend at {target_api_url} is unreachable for suite '{args.suite}'.",
            file=sys.stderr,
        )
        if settings.REQUIRE_BACKEND or args.require_backend:
            return 2

    run_ctx.ensure_directories()
    completed = subprocess.run(cmd, env=env, check=False)
    print(f"[AEGIS] Run directory: {run_ctx.run_dir}")
    print(f"[AEGIS] Metadata: {run_ctx.metadata_path}")
    return int(completed.returncode)


def _reliability_command(args: argparse.Namespace) -> int:
    analyzer = ReliabilityAnalyzer(history_path=args.history)
    records = analyzer.load_records()
    report = analyzer.analyze(records=records)
    json_path, html_path = analyzer.export_reports(output_dir=args.output_dir, report=report)
    print(
        f"[AEGIS] Reliability summary: executions={report.total_executions}, "
        f"unique_tests={report.unique_tests}, pass_rate={report.overall_pass_rate:.1f}%, "
        f"flaky_ratio={report.overall_flaky_rate:.1f}%"
    )
    print(f"[AEGIS] JSON report: {json_path}")
    print(f"[AEGIS] HTML dashboard: {html_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis",
        description="AEGIS Quality Engineering & Test Infrastructure CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute a test suite with run tracking")
    run_parser.add_argument(
        "--suite",
        choices=sorted(SUITE_TO_MARKER.keys()),
        default="all",
        help="Target suite marker to execute",
    )
    run_parser.add_argument("--browser", default=settings.BROWSER_NAME, help="Browser engine")
    run_parser.add_argument("--workers", type=int, default=1, help="Parallel pytest-xdist workers")
    run_parser.add_argument(
        "--environment", default=settings.ENVIRONMENT, help="Target environment"
    )
    run_parser.add_argument("--base-url", default=None, help="Override target SUT BASE_URL")
    run_parser.add_argument("--api-url", default=None, help="Override target SUT API_URL")
    run_parser.add_argument("--run-id", default=None, help="Explicit AEGIS Run ID")
    run_parser.add_argument(
        "--require-backend",
        action="store_true",
        help="Fail immediately if backend /health is unreachable",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved run metadata and pytest command without executing",
    )
    run_parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments forwarded to pytest",
    )

    rel_parser = subparsers.add_parser(
        "reliability",
        help="Generate JSON and HTML reliability reports from execution history",
    )
    rel_parser.add_argument("--history", default=None, help="Path to execution_history.jsonl")
    rel_parser.add_argument("--output-dir", default=None, help="Report output directory")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_command(args)
    if args.command == "reliability":
        return _reliability_command(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
