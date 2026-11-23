"""Unit tests for the AEGIS orchestration CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.config.settings import settings
from framework.execution.cli import build_parser, build_pytest_command, main
from framework.execution.run_context import RunContext


@pytest.mark.unit
class TestExecutionCLI:
    """Verifies CLI command building, dry-run execution, and reliability reporting."""

    def test_build_pytest_command_includes_markers_workers_and_run_reports(
        self, tmp_path: Path
    ) -> None:
        ctx = RunContext(run_id="run-cli-1", runs_root=tmp_path)
        cmd = build_pytest_command(
            suite="ui_mocked",
            workers=4,
            run_context=ctx,
            extra_args=["-k", "checkout"],
        )

        assert "-m" in cmd and "ui_mocked" in cmd
        assert "-n" in cmd and "4" in cmd
        assert any(arg.startswith(f"--junitxml={ctx.run_dir}") for arg in cmd)
        assert any(arg.startswith(f"--alluredir={ctx.allure_results_dir}") for arg in cmd)
        assert "-k" in cmd and "checkout" in cmd

    def test_cli_dry_run_exits_zero_without_creating_run_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "RUNS_DIR", str(tmp_path))
        code = main(
            [
                "run",
                "--suite",
                "unit",
                "--browser",
                "chromium",
                "--workers",
                "2",
                "--environment",
                "ci",
                "--run-id",
                "run-dry-001",
                "--dry-run",
            ]
        )
        assert code == 0
        assert not (tmp_path / "run-dry-001").exists()

    def test_cli_parser_accepts_base_url_and_api_url_overrides(self) -> None:
        parsed = build_parser().parse_args(
            [
                "run",
                "--suite",
                "e2e",
                "--base-url",
                "https://sut.example.com",
                "--api-url",
                "https://api.example.com",
            ]
        )
        assert parsed.base_url == "https://sut.example.com"
        assert parsed.api_url == "https://api.example.com"

    def test_cli_reliability_subcommand_exports_dashboard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "framework.telemetry.reliability.ReliabilityAnalyzer.push_to_backend",
            lambda *args, **kwargs: False,
        )
        history = tmp_path / "execution_history.jsonl"
        history.write_text("", encoding="utf-8")
        out_dir = tmp_path / "reports"

        code = main(
            [
                "reliability",
                "--history",
                str(history),
                "--output-dir",
                str(out_dir),
            ]
        )
        assert code == 0
        assert (out_dir / "reliability_report.json").exists()
        assert (out_dir / "reliability_dashboard.html").exists()
