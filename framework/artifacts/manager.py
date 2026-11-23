"""Centralized test artifact management for screenshots, traces, videos, and logs."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightError

from framework.artifacts.collectors import BrowserConsoleCollector, NetworkFailureCollector
from framework.config.settings import settings
from framework.execution.run_context import RunContext

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page


def sanitize_artifact_name(raw_name: str) -> str:
    """Sanitize a test node ID or identifier into a safe filename stem."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("_")


@dataclass(slots=True)
class CollectedArtifacts:
    """Paths to artifacts saved for a failed test execution."""

    screenshot_path: Path | None = None
    trace_path: Path | None = None
    video_path: Path | None = None
    console_log_path: Path | None = None
    network_failures_path: Path | None = None


class ArtifactManager:
    """Manages per-run directories, Playwright tracing, failure artifacts, and retention."""

    def __init__(
        self,
        run_context: RunContext | None = None,
        max_stored_runs: int | None = None,
    ) -> None:
        self.run_context = run_context or RunContext()
        self.max_stored_runs = (
            max_stored_runs if max_stored_runs is not None else settings.MAX_STORED_RUNS
        )
        self._active_traces: set[int] = set()
        self._failed_video_targets: dict[int, tuple[str, str]] = {}

    def prepare_run_directory(self) -> Path:
        """Create per-run subdirectories and enforce run retention limits."""
        run_dir = self.run_context.ensure_directories()
        self.cleanup_old_runs()
        return run_dir

    def start_tracing(self, context: BrowserContext) -> bool:
        """Start Playwright tracing on a BrowserContext when enabled."""
        if not settings.CAPTURE_TRACE_ON_FAILURE:
            return False
        ctx_id = id(context)
        if ctx_id in self._active_traces:
            return True
        try:
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self._active_traces.add(ctx_id)
            return True
        except (PlaywrightError, RuntimeError):
            return False

    def stop_tracing(
        self,
        context: BrowserContext,
        trace_output_path: Path | None = None,
    ) -> Path | None:
        """Stop Playwright tracing, optionally writing the trace archive to disk."""
        ctx_id = id(context)
        if ctx_id not in self._active_traces:
            return None
        self._active_traces.discard(ctx_id)
        try:
            if trace_output_path is not None:
                trace_output_path.parent.mkdir(parents=True, exist_ok=True)
                context.tracing.stop(path=str(trace_output_path))
                return trace_output_path
            context.tracing.stop()
            return None
        except (PlaywrightError, RuntimeError):
            return None

    def collect_failure_artifacts(
        self,
        node_id: str,
        worker_id: str | None = None,
        page: Page | None = None,
        context: BrowserContext | None = None,
        console_collector: BrowserConsoleCollector | None = None,
        network_collector: NetworkFailureCollector | None = None,
    ) -> CollectedArtifacts:
        """Capture and persist screenshot, trace, console logs, and network failures."""
        self.run_context.ensure_directories()
        worker = worker_id or os.environ.get("PYTEST_XDIST_WORKER", "main")
        stem = f"{worker}_{sanitize_artifact_name(node_id)}"
        collected = CollectedArtifacts()

        if page is not None and settings.CAPTURE_SCREENSHOT_ON_FAILURE:
            screenshot_file = self.run_context.screenshots_dir / f"fail_{stem}.png"
            try:
                png_bytes = page.screenshot(path=str(screenshot_file), full_page=True)
                collected.screenshot_path = screenshot_file
                legacy_dir = Path(settings.ARTIFACTS_DIR)
                legacy_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(screenshot_file, legacy_dir / f"fail_{stem}.png")
                self._attach_allure_bytes(
                    png_bytes,
                    name=f"Failure Screenshot ({worker}: {node_id})",
                    attachment_type="PNG",
                )
            except (PlaywrightError, OSError, RuntimeError):
                pass

        if context is not None and settings.CAPTURE_TRACE_ON_FAILURE:
            trace_file = self.run_context.traces_dir / f"trace_{stem}.zip"
            saved_trace = self.stop_tracing(context, trace_output_path=trace_file)
            if saved_trace is not None and saved_trace.exists():
                collected.trace_path = saved_trace
                self._attach_allure_file(
                    saved_trace,
                    name=f"Playwright Trace ({worker}: {node_id})",
                    extension="zip",
                )

        if console_collector is not None:
            console_file = self.run_context.logs_dir / f"console_{stem}.txt"
            console_text = console_collector.format_text()
            console_file.write_text(console_text, encoding="utf-8")
            collected.console_log_path = console_file
            self._attach_allure_bytes(
                console_text.encode("utf-8"),
                name=f"Browser Console Logs ({worker}: {node_id})",
                attachment_type="TEXT",
            )

        if network_collector is not None:
            network_file = self.run_context.network_dir / f"failed_requests_{stem}.json"
            network_json = network_collector.to_json()
            network_file.write_text(network_json, encoding="utf-8")
            collected.network_failures_path = network_file
            self._attach_allure_bytes(
                network_json.encode("utf-8"),
                name=f"Failed Network Requests ({worker}: {node_id})",
                attachment_type="JSON",
            )

        if page is not None and settings.CAPTURE_VIDEO_ON_FAILURE:
            self._failed_video_targets[id(page)] = (node_id, worker)

        return collected

    def finalize_page_video(self, page: Page) -> Path | None:
        """Persist failure video or discard passed-test recording after page.close()."""
        target = self._failed_video_targets.pop(id(page), None)
        if not settings.CAPTURE_VIDEO_ON_FAILURE:
            return None
        video = getattr(page, "video", None)
        if video is None:
            return None
        if target is None:
            with contextlib.suppress(PlaywrightError, OSError, RuntimeError):
                video.delete()
            return None

        node_id, worker = target
        saved = self.save_video_on_failure(page=page, node_id=node_id, worker_id=worker)
        if saved is not None and saved.exists():
            self._attach_allure_file(
                saved,
                name=f"Failure Video ({worker}: {node_id})",
                extension="webm",
            )
        with contextlib.suppress(PlaywrightError, OSError, RuntimeError):
            video.delete()
        return saved

    def save_video_on_failure(
        self,
        page: Page,
        node_id: str,
        worker_id: str | None = None,
    ) -> Path | None:
        """Persist recorded Playwright video for a failed test if recording is enabled."""
        if not settings.CAPTURE_VIDEO_ON_FAILURE:
            return None
        video = getattr(page, "video", None)
        if video is None:
            return None
        worker = worker_id or os.environ.get("PYTEST_XDIST_WORKER", "main")
        stem = f"{worker}_{sanitize_artifact_name(node_id)}"
        target = self.run_context.videos_dir / f"video_{stem}.webm"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            video.save_as(str(target))
            return target
        except (PlaywrightError, OSError, RuntimeError):
            return None

    def cleanup_old_runs(self, max_runs: int | None = None) -> list[Path]:
        """Remove oldest run directories exceeding max_runs retention."""
        limit = self.max_stored_runs if max_runs is None else max_runs
        if limit < 1 or not self.run_context.runs_root.exists():
            return []

        run_dirs = [
            p
            for p in self.run_context.runs_root.iterdir()
            if p.is_dir() and p.name != self.run_context.run_id
        ]
        # Keep active run plus (limit - 1) most recently modified historical runs
        run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        keep_historical = max(0, limit - 1)
        to_remove = run_dirs[keep_historical:]

        removed: list[Path] = []
        for old_dir in to_remove:
            shutil.rmtree(old_dir, ignore_errors=True)
            removed.append(old_dir)
        return removed

    @staticmethod
    def _attach_allure_bytes(content: bytes, name: str, attachment_type: str) -> None:
        try:
            import allure

            allure_type = getattr(allure.attachment_type, attachment_type, None)
            if allure_type is not None:
                allure.attach(content, name=name, attachment_type=allure_type)
        except (ImportError, RuntimeError, TypeError, AttributeError):
            pass

    @staticmethod
    def _attach_allure_file(path: Path, name: str, extension: str) -> None:
        try:
            import allure

            allure.attach.file(str(path), name=name, extension=extension)
        except (ImportError, RuntimeError, TypeError, AttributeError):
            pass
