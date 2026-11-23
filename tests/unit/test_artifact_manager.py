"""Unit tests for RunContext, ExecutionMetadata, collectors, and ArtifactManager."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error as PlaywrightError

from framework.artifacts.collectors import BrowserConsoleCollector, NetworkFailureCollector
from framework.artifacts.manager import ArtifactManager
from framework.execution.metadata import ExecutionMetadata
from framework.execution.run_context import RunContext


@pytest.mark.unit
class TestArtifactManagement:
    """Validates M1 reliability components without requiring live browser or backend."""

    def test_run_context_creates_isolated_run_directories(self, tmp_path: Path) -> None:
        ctx = RunContext(run_id="run-test-001", runs_root=tmp_path)
        run_dir = ctx.ensure_directories()

        assert run_dir == tmp_path / "run-test-001"
        for sub in (
            ctx.screenshots_dir,
            ctx.traces_dir,
            ctx.videos_dir,
            ctx.network_dir,
            ctx.logs_dir,
            ctx.ai_diagnostics_dir,
            ctx.allure_results_dir,
        ):
            assert sub.is_dir()

    def test_execution_metadata_roundtrip(self, tmp_path: Path) -> None:
        meta = ExecutionMetadata(
            run_id="run-meta-1",
            environment="ci",
            browser="chromium",
            workers=4,
            started_at="2026-11-16T12:00:00+00:00",
            finished_at="2026-11-16T12:00:10+00:00",
            duration_ms=10000.0,
            total_tests=10,
            passed=9,
            failed=1,
            skipped=0,
        )
        out = meta.save(tmp_path / "metadata.json")
        loaded = ExecutionMetadata.load(out)

        assert loaded.run_id == "run-meta-1"
        assert loaded.workers == 4
        assert loaded.failed == 1

    def test_console_and_network_collectors_format_events(self) -> None:
        console = BrowserConsoleCollector()
        fake_msg = MagicMock()
        fake_msg.type = "error"
        fake_msg.text = "Uncaught TypeError: cannot read property"
        fake_msg.location = {"url": "http://localhost:8080/app.js", "lineNumber": 42}
        console._on_console(fake_msg)
        console._on_page_error(RuntimeError("Boom"))

        rendered = console.format_text()
        assert "[ERROR] Uncaught TypeError" in rendered
        assert "[PAGEERROR] Boom" in rendered

        network = NetworkFailureCollector()
        fake_req = MagicMock()
        fake_req.method = "POST"
        fake_req.url = "http://localhost:3000/api/v1/orders/checkout"
        fake_req.failure = "net::ERR_CONNECTION_REFUSED"
        fake_req.resource_type = "fetch"
        network._on_request_failed(fake_req)

        fake_resp = MagicMock()
        fake_resp.status = 500
        fake_resp.status_text = "Internal Server Error"
        fake_resp.url = "http://localhost:3000/api/v1/products"
        fake_resp.request.method = "GET"
        fake_resp.request.resource_type = "fetch"
        network._on_response(fake_resp)

        serialized = network.to_json()
        assert "ERR_CONNECTION_REFUSED" in serialized
        assert '"status": 500' in serialized

    def test_artifact_manager_trace_lifecycle_and_failure_collection(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "framework.artifacts.manager.settings.ARTIFACTS_DIR", str(tmp_path / "art")
        )
        monkeypatch.setattr("framework.artifacts.manager.settings.CAPTURE_VIDEO_ON_FAILURE", True)
        run_ctx = RunContext(run_id="run-active", runs_root=tmp_path / "runs")
        manager = ArtifactManager(run_context=run_ctx, max_stored_runs=2)

        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.screenshot.return_value = b"PNGDATA"
        mock_page.video.save_as.side_effect = lambda p: Path(p).write_bytes(b"WEBMDATA")

        console = BrowserConsoleCollector()
        console._on_page_error(ValueError("Reference broken"))
        network = NetworkFailureCollector()

        assert manager.start_tracing(mock_context) is True
        mock_context.tracing.start.assert_called_once_with(
            screenshots=True, snapshots=True, sources=True
        )

        def fake_stop(**kwargs):
            if "path" in kwargs:
                Path(kwargs["path"]).write_bytes(b"ZIPTRACE")

        mock_context.tracing.stop.side_effect = fake_stop

        artifacts = manager.collect_failure_artifacts(
            node_id="tests/ui/test_demo.py::test_fail",
            worker_id="gw1",
            page=mock_page,
            context=mock_context,
            console_collector=console,
            network_collector=network,
        )

        assert artifacts.screenshot_path is not None
        assert artifacts.trace_path is not None and artifacts.trace_path.exists()
        # Video must be deferred until after page.close()
        assert artifacts.video_path is None
        saved_video = manager.finalize_page_video(mock_page)
        assert saved_video is not None and saved_video.exists()
        mock_page.video.delete.assert_called_once()
        assert artifacts.console_log_path is not None and artifacts.console_log_path.exists()
        assert (
            artifacts.network_failures_path is not None and artifacts.network_failures_path.exists()
        )
        # Stopping tracing a second time on teardown must be a no-op
        assert manager.stop_tracing(mock_context) is None

    def test_finalize_page_video_discards_passed_and_handles_playwright_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("framework.artifacts.manager.settings.CAPTURE_VIDEO_ON_FAILURE", True)
        run_ctx = RunContext(run_id="run-video-guard", runs_root=tmp_path / "runs")
        manager = ArtifactManager(run_context=run_ctx)

        passed_page = MagicMock()
        assert manager.finalize_page_video(passed_page) is None
        passed_page.video.delete.assert_called_once()

        failed_page = MagicMock()
        failed_page.video.save_as.side_effect = PlaywrightError("Page is not yet closed")
        manager._failed_video_targets[id(failed_page)] = ("tests/ui/test_x.py::test_y", "gw0")
        assert manager.finalize_page_video(failed_page) is None
        failed_page.video.delete.assert_called_once()

    def test_cleanup_old_runs_enforces_retention(self, tmp_path: Path) -> None:
        runs_root = tmp_path / "runs"
        for idx, name in enumerate(("run-old-1", "run-old-2", "run-recent")):
            d = runs_root / name
            d.mkdir(parents=True)
            os.utime(d, (1000 + idx * 100, 1000 + idx * 100))

        active_ctx = RunContext(run_id="run-current", runs_root=runs_root)
        active_ctx.ensure_directories()
        manager = ArtifactManager(run_context=active_ctx, max_stored_runs=2)
        removed = manager.cleanup_old_runs()

        removed_names = {p.name for p in removed}
        assert removed_names == {"run-old-1", "run-old-2"}
        assert (runs_root / "run-recent").exists()
        assert (runs_root / "run-current").exists()
