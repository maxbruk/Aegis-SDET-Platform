"""Xdist-safe artifact collection and failure intelligence hooks for pytest."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Any

from playwright.sync_api import BrowserContext, Page
from playwright.sync_api import Error as PlaywrightError

from framework.ai.analyzer import FailureIntelligenceAnalyzer
from framework.artifacts.collectors import BrowserConsoleCollector, NetworkFailureCollector
from framework.artifacts.manager import ArtifactManager, CollectedArtifacts, sanitize_artifact_name
from framework.config.settings import settings

logger = logging.getLogger(__name__)

_PAGE_FIXTURE_NAMES = (
    "page",
    "mocked_page",
    "integration_page",
    "authenticated_page",
    "mocked_authenticated_page",
    "admin_page",
    "mocked_admin_page",
)
_PAGE_OBJECT_FIXTURE_NAMES = (
    "storefront_page",
    "mocked_storefront_page",
    "integration_storefront_page",
)


def sanitize_node_id(node_id: str) -> str:
    """Convert pytest node ID into a cross-platform safe filename fragment."""
    return sanitize_artifact_name(node_id)


def resolve_page_from_item(item: Any) -> Page | None:
    """Extract the active Playwright Page instance from test function arguments."""
    for name in _PAGE_FIXTURE_NAMES:
        candidate = item.funcargs.get(name)
        if candidate is not None:
            return candidate
    for name in _PAGE_OBJECT_FIXTURE_NAMES:
        page_obj = item.funcargs.get(name)
        if page_obj is not None and hasattr(page_obj, "page"):
            return page_obj.page
    return None


def collect_test_failure_artifacts(
    item: Any,
    error_text: str = "",
) -> tuple[CollectedArtifacts | None, str | None]:
    """Collect failure artifacts and run AI failure intelligence, returning failure category."""
    page_instance = resolve_page_from_item(item)
    manager: ArtifactManager | None = item.funcargs.get("artifact_manager")
    context: BrowserContext | None = item.funcargs.get("context")
    console_collector: BrowserConsoleCollector | None = item.funcargs.get("console_collector")
    network_collector: NetworkFailureCollector | None = item.funcargs.get("network_collector")

    active_manager = manager or ArtifactManager()
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
    collected: CollectedArtifacts | None = None

    if page_instance is not None or console_collector is not None or network_collector is not None:
        collected = active_manager.collect_failure_artifacts(
            node_id=item.nodeid,
            worker_id=worker_id,
            page=page_instance,
            context=context,
            console_collector=console_collector,
            network_collector=network_collector,
        )

    failure_category: str | None = None
    if settings.AI_ENABLED and error_text:
        try:
            artifact_map: dict[str, str] = {}
            if collected is not None:
                for key, val in (
                    ("screenshot", collected.screenshot_path),
                    ("trace", collected.trace_path),
                    ("console_log", collected.console_log_path),
                    ("network_failures", collected.network_failures_path),
                ):
                    if val is not None:
                        artifact_map[key] = str(val)

            network_entries = (
                [asdict(e) for e in network_collector.entries] if network_collector else []
            )
            console_text = console_collector.format_text() if console_collector else ""
            ai_report = FailureIntelligenceAnalyzer(
                run_context=active_manager.run_context
            ).analyze_failure(
                test_id=item.nodeid,
                error_message=error_text,
                console_logs=console_text,
                failed_network_requests=network_entries,
                page=page_instance,
                artifact_paths=artifact_map,
            )
            failure_category = ai_report.classification.category.value
            ArtifactManager._attach_allure_bytes(
                ai_report.model_dump_json(indent=2).encode("utf-8"),
                name=f"AI Failure Intelligence ({item.name})",
                attachment_type="JSON",
            )
        except (PlaywrightError, OSError, RuntimeError, ValueError) as exc:
            logger.debug("Failure intelligence analysis skipped: %s", exc)

    return collected, failure_category
