"""Test reliability tracking, comparable-condition flakiness scoring, and reporting."""

from __future__ import annotations

import functools
import html
import logging
import math
import os
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from framework.config.settings import settings

logger = logging.getLogger(__name__)


class TestExecutionRecord(BaseModel):
    """Single test execution event appended to execution history."""

    __test__ = False

    test_id: str
    run_id: str
    status: Literal["passed", "failed", "skipped", "error"]
    duration_ms: float = Field(ge=0.0)
    browser: str = "chromium"
    environment: str = "local"
    git_sha: str = ""
    worker: str = "main"
    failure_category: str | None = None
    retry_count: int = Field(default=0, ge=0)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TestReliabilityMetrics(BaseModel):
    """Aggregated reliability and latency statistics for a single test."""

    __test__ = False

    test_id: str
    total_runs: int
    passed: int
    failed: int
    skipped: int
    pass_rate: float
    failure_rate: float
    flaky_rate: float
    avg_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    duration_regression: bool = False


class ReliabilityReport(BaseModel):
    """Project-wide reliability summary across recorded test runs."""

    generated_at: str
    total_executions: int
    unique_tests: int
    overall_pass_rate: float
    overall_flaky_rate: float
    suite_p50_duration_ms: float = 0.0
    suite_p95_duration_ms: float = 0.0
    most_frequently_failing_tests: list[dict[str, Any]]
    failure_categories: dict[str, int]
    duration_regressions: list[dict[str, Any]]
    tests: list[TestReliabilityMetrics]


@functools.lru_cache(maxsize=1)
def resolve_git_sha() -> str:
    """Resolve short git commit SHA from environment variables or local git HEAD."""
    for env_var in ("AEGIS_GIT_SHA", "GITHUB_SHA"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val[:12]
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.5,
        ).strip()
        if output:
            return output
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def _atomic_write_text(target: Path, content: str) -> None:
    """Atomically write text to target using a temp file in the same directory."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp_", suffix=".jsonl")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute linear-interpolated percentile (0..100) from sorted numeric samples."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(sorted_values[low])
    weight = rank - low
    return float(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


class ReliabilityAnalyzer:
    """Collects test execution history and derives pass, flaky, and latency metrics."""

    def __init__(
        self,
        history_path: str | Path | None = None,
        max_records: int = 2000,
    ) -> None:
        base_dir = Path(settings.RELIABILITY_DIR)
        self.history_path = (
            Path(history_path) if history_path else base_dir / "execution_history.jsonl"
        )
        self.max_records = max_records

    def record_execution(self, record: TestExecutionRecord) -> None:
        """Append one test execution record to the JSONL history file (O(1) append)."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")

    def upsert_execution(self, record: TestExecutionRecord) -> None:
        """Replace an existing (run_id, test_id) record atomically or append if missing."""
        if not self.history_path.exists():
            self.record_execution(record)
            return
        lines = [
            ln for ln in self.history_path.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        updated = False
        for idx in range(len(lines) - 1, -1, -1):
            try:
                existing = TestExecutionRecord.model_validate_json(lines[idx])
            except ValueError:
                continue
            if existing.run_id == record.run_id and existing.test_id == record.test_id:
                lines[idx] = record.model_dump_json()
                updated = True
                break
        if not updated:
            lines.append(record.model_dump_json())
        if self.max_records > 0 and len(lines) > self.max_records:
            lines = lines[-self.max_records :]
        _atomic_write_text(self.history_path, "\n".join(lines) + "\n")

    def trim_history(self) -> None:
        """Atomically enforce max_records retention on execution history."""
        if self.max_records <= 0 or not self.history_path.exists():
            return
        lines = [
            ln for ln in self.history_path.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        if len(lines) > self.max_records:
            trimmed = "\n".join(lines[-self.max_records :]) + "\n"
            _atomic_write_text(self.history_path, trimmed)

    def load_records(self) -> list[TestExecutionRecord]:
        """Load all persisted execution records from disk."""
        if not self.history_path.exists():
            return []
        records: list[TestExecutionRecord] = []
        for raw_line in self.history_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(TestExecutionRecord.model_validate_json(line))
            except ValueError:
                continue
        return records

    @staticmethod
    def _compute_comparable_flaky_rate(records: list[TestExecutionRecord]) -> float:
        """Compute flakiness only across comparable (browser, environment, git_sha) runs or retries."""
        if not records:
            return 0.0

        buckets: dict[tuple[str, str, str], list[TestExecutionRecord]] = defaultdict(list)
        for rec in records:
            buckets[(rec.browser, rec.environment, rec.git_sha)].append(rec)

        comparable_total = 0
        flaky_executions = 0
        for bucket_records in buckets.values():
            non_skipped = [r for r in bucket_records if r.status != "skipped"]
            if len(non_skipped) >= 2:
                statuses = {"passed" if r.status == "passed" else "failed" for r in non_skipped}
                if len(statuses) > 1:
                    comparable_total += len(non_skipped)
                    minor_count = min(
                        sum(1 for r in non_skipped if r.status == "passed"),
                        sum(1 for r in non_skipped if r.status != "passed"),
                    )
                    flaky_executions += minor_count
                    continue
            # Also capture explicit retry passes within a comparable run
            retry_passes = sum(1 for r in non_skipped if r.status == "passed" and r.retry_count > 0)
            if retry_passes > 0:
                comparable_total += len(non_skipped)
                flaky_executions += retry_passes

        if comparable_total == 0:
            return 0.0
        return round((flaky_executions / comparable_total) * 100.0, 2)

    def analyze(self, records: list[TestExecutionRecord] | None = None) -> ReliabilityReport:
        """Compute per-test and aggregate reliability metrics."""
        all_records = self.load_records() if records is None else records
        by_test: dict[str, list[TestExecutionRecord]] = defaultdict(list)
        categories: Counter[str] = Counter()

        for rec in all_records:
            by_test[rec.test_id].append(rec)
            if rec.status in ("failed", "error") and rec.failure_category:
                categories[rec.failure_category] += 1

        test_metrics: list[TestReliabilityMetrics] = []
        duration_regressions: list[dict[str, Any]] = []
        failing_summary: list[dict[str, Any]] = []

        for test_id, test_recs in sorted(by_test.items()):
            total = len(test_recs)
            passed = sum(1 for r in test_recs if r.status == "passed")
            failed = sum(1 for r in test_recs if r.status in ("failed", "error"))
            skipped = sum(1 for r in test_recs if r.status == "skipped")
            executed = passed + failed

            pass_rate = round((passed / executed) * 100.0, 2) if executed else 0.0
            failure_rate = round((failed / executed) * 100.0, 2) if executed else 0.0
            flaky_rate = self._compute_comparable_flaky_rate(test_recs)

            durations = sorted(r.duration_ms for r in test_recs if r.status != "skipped")
            avg_ms = round(sum(durations) / len(durations), 2) if durations else 0.0
            p50_ms = round(_percentile(durations, 50.0), 2)
            p95_ms = round(_percentile(durations, 95.0), 2)

            regression = False
            non_skipped_chronological = [r for r in test_recs if r.status != "skipped"]
            if len(non_skipped_chronological) >= 3:
                baseline_p50 = _percentile(
                    sorted(r.duration_ms for r in non_skipped_chronological[:-1]), 50.0
                )
                latest = non_skipped_chronological[-1].duration_ms
                if latest > baseline_p50 * 1.5 and latest > baseline_p50 + 100.0:
                    regression = True
                    duration_regressions.append(
                        {
                            "test_id": test_id,
                            "baseline_p50_ms": round(baseline_p50, 2),
                            "latest_duration_ms": round(latest, 2),
                        }
                    )

            metrics = TestReliabilityMetrics(
                test_id=test_id,
                total_runs=total,
                passed=passed,
                failed=failed,
                skipped=skipped,
                pass_rate=pass_rate,
                failure_rate=failure_rate,
                flaky_rate=flaky_rate,
                avg_duration_ms=avg_ms,
                p50_duration_ms=p50_ms,
                p95_duration_ms=p95_ms,
                duration_regression=regression,
            )
            test_metrics.append(metrics)

            if failed > 0:
                failing_summary.append(
                    {
                        "test_id": test_id,
                        "failed_count": failed,
                        "total_runs": total,
                        "failure_rate": failure_rate,
                    }
                )

        failing_summary.sort(key=lambda item: (-item["failed_count"], -item["failure_rate"]))
        total_exec = len(all_records)
        total_passed = sum(1 for r in all_records if r.status == "passed")
        total_executed = sum(1 for r in all_records if r.status != "skipped")
        overall_pass = round((total_passed / total_executed) * 100.0, 2) if total_executed else 0.0
        flaky_tests = [m for m in test_metrics if m.flaky_rate > 0.0]
        overall_flaky = (
            round((len(flaky_tests) / len(test_metrics)) * 100.0, 2) if test_metrics else 0.0
        )

        raw_durations = sorted(r.duration_ms for r in all_records if r.status != "skipped")
        suite_p50_ms = round(_percentile(raw_durations, 50.0), 2) if raw_durations else 0.0
        suite_p95_ms = round(_percentile(raw_durations, 95.0), 2) if raw_durations else 0.0

        return ReliabilityReport(
            generated_at=datetime.now(UTC).isoformat(),
            total_executions=total_exec,
            unique_tests=len(test_metrics),
            overall_pass_rate=overall_pass,
            overall_flaky_rate=overall_flaky,
            suite_p50_duration_ms=suite_p50_ms,
            suite_p95_duration_ms=suite_p95_ms,
            most_frequently_failing_tests=failing_summary[:10],
            failure_categories=dict(categories),
            duration_regressions=duration_regressions,
            tests=test_metrics,
        )

    def push_to_backend(
        self,
        report: ReliabilityReport,
        records: list[TestExecutionRecord],
        api_url: str | None = None,
    ) -> bool:
        """Push aggregated reliability metrics and test records to the Go telemetry ingest API."""
        target_url = f"{(api_url or settings.API_URL).rstrip('/')}/api/v1/telemetry/ingest"
        payload = {
            "run_id": records[-1].run_id if records else "summary",
            "summary": {
                "total_executions": report.total_executions,
                "unique_tests": report.unique_tests,
                "pass_rate": report.overall_pass_rate,
                "flaky_rate": report.overall_flaky_rate,
                "p50_ms": report.suite_p50_duration_ms,
                "p95_ms": report.suite_p95_duration_ms,
            },
            "failure_categories": report.failure_categories,
            "records": [
                {
                    "run_id": rec.run_id,
                    "test_id": rec.test_id,
                    "suite": rec.test_id.split("/")[1] if "/" in rec.test_id else "all",
                    "status": rec.status,
                    "duration_ms": rec.duration_ms,
                    "browser": rec.browser,
                    "worker": rec.worker,
                    "environment": rec.environment,
                    "failure_category": rec.failure_category or "",
                }
                for rec in records[-500:]
            ],
        }
        try:
            response = httpx.post(target_url, json=payload, timeout=1.5)
            return response.status_code == 200
        except httpx.HTTPError as exc:
            logger.debug("Skipping backend telemetry push (offline): %s", exc)
            return False

    def export_reports(
        self,
        output_dir: str | Path | None = None,
        push_telemetry: bool = True,
        report: ReliabilityReport | None = None,
    ) -> tuple[Path, Path]:
        """Write JSON/HTML reliability reports and forward telemetry when backend is available."""
        self.trim_history()
        target_dir = Path(output_dir) if output_dir else Path(settings.RELIABILITY_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        records = self.load_records()
        active_report = report if report is not None else self.analyze(records=records)

        json_path = target_dir / "reliability_report.json"
        json_path.write_text(active_report.model_dump_json(indent=2), encoding="utf-8")

        html_path = target_dir / "reliability_dashboard.html"
        html_path.write_text(self._render_html(active_report), encoding="utf-8")

        if push_telemetry:
            self.push_to_backend(active_report, records)
        return json_path, html_path

    @staticmethod
    def _render_html(report: ReliabilityReport) -> str:
        median_p50 = report.suite_p50_duration_ms
        tail_p95 = report.suite_p95_duration_ms

        def _badge(t: TestReliabilityMetrics) -> str:
            if t.duration_regression:
                return '<span class="pill pill-warn">REGRESSION</span>'
            if t.flaky_rate > 0:
                return '<span class="pill pill-warn">FLAKY</span>'
            if t.failure_rate > 0:
                return '<span class="pill pill-fail">FAILING</span>'
            return '<span class="pill pill-ok">HEALTHY</span>'

        rows = "\n".join(
            f"<tr>"
            f"<td class='mono'>{html.escape(t.test_id)}</td>"
            f"<td>{t.total_runs}</td>"
            f"<td>{t.passed} / {t.failed}</td>"
            f"<td>{t.pass_rate:.1f}%</td>"
            f"<td>{t.flaky_rate:.1f}%</td>"
            f"<td class='mono'>{t.avg_duration_ms:.1f} ms</td>"
            f"<td class='mono'>{t.p50_duration_ms:.1f} ms</td>"
            f"<td class='mono'>{t.p95_duration_ms:.1f} ms</td>"
            f"<td>{_badge(t)}</td>"
            f"</tr>"
            for t in report.tests
        )

        if report.failure_categories:
            cat_chips = "".join(
                f"<span class='chip'><strong>{html.escape(k)}</strong>: {v}</span>"
                for k, v in sorted(report.failure_categories.items())
            )
        else:
            cat_chips = "<span class='muted'>No failures recorded across execution history</span>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AEGIS Reliability & Observability Dashboard</title>
  <style>
    :root {{
      --bg: #f8fafc; --surface: #ffffff; --border: #e2e8f0;
      --text: #0f172a; --muted: #64748b; --accent: #0f172a;
      --ok-bg: #dcfce7; --ok-fg: #166534;
      --warn-bg: #fef3c7; --warn-fg: #92400e;
      --fail-bg: #fee2e2; --fail-fg: #991b1b;
    }}
    body {{ font-family: Inter, system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 2rem; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; }}
    header {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; }}
    h1 {{ margin: 0; font-size: 1.5rem; letter-spacing: -0.02em; }}
    .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.85rem; margin-bottom: 1.25rem; }}
    .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.9rem 1rem; }}
    .card-label {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 600; }}
    .card-val {{ font-size: 1.35rem; font-weight: 700; margin-top: 0.35rem; font-variant-numeric: tabular-nums; }}
    .panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; }}
    .panel-title {{ font-size: 0.85rem; font-weight: 600; margin: 0 0 0.65rem 0; }}
    .chip {{ display: inline-block; background: #f1f5f9; border: 1px solid var(--border); border-radius: 999px; padding: 0.2rem 0.7rem; font-size: 0.8rem; margin-right: 0.5rem; }}
    .muted {{ color: var(--muted); font-size: 0.85rem; }}
    .table-wrap {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; table-layout: fixed; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 0.55rem 0.6rem; text-align: left; white-space: nowrap; }}
    th {{ background: #f1f5f9; font-weight: 600; color: #334155; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    th:first-child, td:first-child {{ width: 42%; white-space: normal; overflow-wrap: anywhere; }}
    .mono {{ font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace; font-size: 0.75rem; }}
    .pill {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.7rem; font-weight: 700; }}
    .pill-ok {{ background: var(--ok-bg); color: var(--ok-fg); }}
    .pill-warn {{ background: var(--warn-bg); color: var(--warn-fg); }}
    .pill-fail {{ background: var(--fail-bg); color: var(--fail-fg); }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>AEGIS Test Reliability &amp; Observability Dashboard</h1>
        <div class="subtitle">Generated {html.escape(report.generated_at)}</div>
      </div>
      <span class="pill pill-ok">OBSERVABILITY ACTIVE</span>
    </header>
    <div class="cards">
      <div class="card"><div class="card-label">Executions</div><div class="card-val">{report.total_executions}</div></div>
      <div class="card"><div class="card-label">Unique Tests</div><div class="card-val">{report.unique_tests}</div></div>
      <div class="card"><div class="card-label">Pass Rate</div><div class="card-val">{report.overall_pass_rate:.1f}%</div></div>
      <div class="card"><div class="card-label">Flaky Ratio</div><div class="card-val">{report.overall_flaky_rate:.1f}%</div></div>
      <div class="card"><div class="card-label">Suite Median P50</div><div class="card-val">{median_p50:.1f} ms</div></div>
      <div class="card"><div class="card-label">Suite Tail P95</div><div class="card-val">{tail_p95:.1f} ms</div></div>
    </div>
    <div class="panel">
      <div class="panel-title">Failure Categories Breakdown</div>
      <div>{cat_chips}</div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Test Node ID</th><th>Runs</th><th>Pass / Fail</th><th>Pass Rate</th>
            <th>Flaky Rate</th><th>Avg</th><th>P50</th><th>P95</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
