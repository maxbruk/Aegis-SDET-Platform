"""Unit tests for ReliabilityAnalyzer metrics, comparable flakiness, and dashboard exports."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.telemetry.reliability import ReliabilityAnalyzer, TestExecutionRecord


@pytest.mark.unit
class TestReliabilityAnalyzer:
    """Verifies pass/fail rates, comparable flaky detection, percentiles, and regressions."""

    def test_single_failure_or_consistent_failure_is_not_marked_flaky(self, tmp_path: Path) -> None:
        analyzer = ReliabilityAnalyzer(history_path=tmp_path / "history.jsonl")
        # Consistent 100% failure across 3 comparable runs -> not flaky
        for i in range(3):
            analyzer.record_execution(
                TestExecutionRecord(
                    test_id="tests/api/test_broken.py::test_always_fails",
                    run_id=f"run-{i}",
                    status="failed",
                    duration_ms=200.0 + i * 10,
                    browser="chromium",
                    environment="ci",
                    failure_category="assertion_failure",
                )
            )
        # Single isolated run -> not flaky
        analyzer.record_execution(
            TestExecutionRecord(
                test_id="tests/api/test_single.py::test_once",
                run_id="run-0",
                status="failed",
                duration_ms=100.0,
                browser="chromium",
                environment="ci",
                failure_category="network_failure",
            )
        )

        report = analyzer.analyze()
        metrics_by_id = {m.test_id: m for m in report.tests}

        assert metrics_by_id["tests/api/test_broken.py::test_always_fails"].flaky_rate == 0.0
        assert metrics_by_id["tests/api/test_broken.py::test_always_fails"].failure_rate == 100.0
        assert metrics_by_id["tests/api/test_single.py::test_once"].flaky_rate == 0.0
        assert report.failure_categories == {"assertion_failure": 3, "network_failure": 1}

    def test_comparable_mixed_outcomes_calculate_flaky_rate_and_regressions(
        self, tmp_path: Path
    ) -> None:
        analyzer = ReliabilityAnalyzer(history_path=tmp_path / "history.jsonl")
        # 3 passes + 1 fail under identical (chromium, ci) -> 25% flaky rate + duration regression
        durations = [100.0, 110.0, 120.0, 600.0]
        statuses: list[str] = ["passed", "passed", "failed", "passed"]
        for i, (status, dur) in enumerate(zip(statuses, durations, strict=True)):
            analyzer.record_execution(
                TestExecutionRecord(
                    test_id="tests/ui/test_flaky.py::test_checkout",
                    run_id=f"run-{i}",
                    status=status,  # type: ignore[arg-type]
                    duration_ms=dur,
                    browser="chromium",
                    environment="ci",
                    failure_category="timeout_failure" if status == "failed" else None,
                )
            )

        report = analyzer.analyze()
        assert len(report.tests) == 1
        m = report.tests[0]
        assert m.pass_rate == 75.0
        assert m.flaky_rate == 25.0
        assert m.p50_duration_ms == 115.0
        assert m.p95_duration_ms > 500.0
        assert m.duration_regression is True
        assert len(report.duration_regressions) == 1

        json_path, html_path = analyzer.export_reports(
            output_dir=tmp_path / "out", push_telemetry=False
        )
        assert json_path.exists()
        assert html_path.exists()
        assert "test_checkout" in html_path.read_text(encoding="utf-8")

    def test_push_to_backend_handles_offline_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = ReliabilityAnalyzer(history_path=tmp_path / "history.jsonl")
        report = analyzer.analyze()

        def fake_post(*args, **kwargs):
            del args, kwargs

            class Resp:
                status_code = 200

            return Resp()

        monkeypatch.setattr("framework.telemetry.reliability.httpx.post", fake_post)
        assert analyzer.push_to_backend(report, []) is True

    def test_raw_suite_percentiles_and_git_sha_flakiness_isolation(self, tmp_path: Path) -> None:
        analyzer = ReliabilityAnalyzer(history_path=tmp_path / "history.jsonl")
        # 9 fast executions for test_fast (10ms) + 1 slow execution for test_slow (1000ms).
        # Raw sample P50 must equal 10.0 (not percentile-of-percentiles 505.0).
        for i in range(9):
            analyzer.record_execution(
                TestExecutionRecord(
                    test_id="tests/unit/test_fast.py::test_fast",
                    run_id=f"run-{i}",
                    status="passed",
                    duration_ms=10.0,
                    browser="chromium",
                    environment="ci",
                    git_sha="commit-a",
                )
            )
        analyzer.record_execution(
            TestExecutionRecord(
                test_id="tests/e2e/test_slow.py::test_slow",
                run_id="run-0",
                status="failed",
                duration_ms=1000.0,
                browser="chromium",
                environment="ci",
                git_sha="commit-a",
            )
        )
        # Fixing test_slow on a new commit must not make commit-a -> commit-b look flaky
        analyzer.record_execution(
            TestExecutionRecord(
                test_id="tests/e2e/test_slow.py::test_slow",
                run_id="run-1",
                status="passed",
                duration_ms=1000.0,
                browser="chromium",
                environment="ci",
                git_sha="commit-b",
            )
        )

        report = analyzer.analyze()
        slow_metrics = next(m for m in report.tests if m.test_id.endswith("test_slow"))
        assert slow_metrics.flaky_rate == 0.0
        assert report.overall_flaky_rate == 0.0
        assert report.suite_p50_duration_ms == 10.0
        assert report.suite_p95_duration_ms == 1000.0
