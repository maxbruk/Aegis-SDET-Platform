"""AEGIS Pytest configuration entrypoint: exposes modular fixtures and lifecycle hooks."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Literal

import pytest

from framework.artifacts.manager import ArtifactManager
from framework.config.settings import settings
from framework.execution.metadata import ExecutionMetadata
from framework.execution.run_context import RunContext
from framework.telemetry.reliability import (
    ReliabilityAnalyzer,
    TestExecutionRecord,
    resolve_git_sha,
)
from tests.fixtures.api import (
    api_client,
    auth_api,
    backend_health,
    cart_api,
    orders_api,
    products_api,
)
from tests.fixtures.authentication import (
    admin_page,
    authenticated_page,
    mocked_admin_page,
    mocked_authenticated_page,
)
from tests.fixtures.browser import (
    artifact_manager,
    browser,
    console_collector,
    context,
    integration_page,
    integration_storefront_page,
    mocked_page,
    mocked_storefront_page,
    network_collector,
    page,
    playwright_instance,
    run_context,
    storefront_page,
)
from tests.fixtures.quality_tools import (
    axe_auditor,
    cdp_collector,
    chaos_injector,
    data_factory,
    test_data_manager,
    visual_checker,
)
from tests.fixtures.server import live_server
from tests.support.artifact_helpers import collect_test_failure_artifacts

__all__ = [
    "admin_page",
    "api_client",
    "artifact_manager",
    "auth_api",
    "authenticated_page",
    "axe_auditor",
    "backend_health",
    "browser",
    "cart_api",
    "cdp_collector",
    "chaos_injector",
    "console_collector",
    "context",
    "data_factory",
    "integration_page",
    "integration_storefront_page",
    "live_server",
    "mocked_admin_page",
    "mocked_authenticated_page",
    "mocked_page",
    "mocked_storefront_page",
    "network_collector",
    "orders_api",
    "page",
    "playwright_instance",
    "products_api",
    "run_context",
    "storefront_page",
    "test_data_manager",
    "visual_checker",
]


_IS_CONTROLLER = True
_RECORDED_NODES: dict[str, str] = {}


def _is_collect_or_help(config: pytest.Config) -> bool:
    return bool(
        getattr(config.option, "collectonly", False) or getattr(config.option, "help", False)
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    global _IS_CONTROLLER
    workerinput = getattr(config, "workerinput", None)
    if workerinput and "aegis_run_id" in workerinput:
        _IS_CONTROLLER = False
        os.environ["AEGIS_RUN_ID"] = workerinput["aegis_run_id"]
    else:
        _IS_CONTROLLER = True
        _RECORDED_NODES.clear()
        if _is_collect_or_help(config):
            return
        run_id = RunContext.resolve_run_id()
        run_ctx = RunContext(run_id=run_id)
        ArtifactManager(run_ctx).prepare_run_directory()
        if not getattr(config.option, "xmlpath", None):
            config.option.xmlpath = str(run_ctx.run_dir / "junit.xml")
        config._aegis_started_at = datetime.now(UTC).isoformat()  # type: ignore[attr-defined]
        config._aegis_start_perf = time.perf_counter()  # type: ignore[attr-defined]


def pytest_configure_node(node) -> None:
    node.workerinput["aegis_run_id"] = RunContext.resolve_run_id()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    del call
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" or (report.failed and report.when in ("setup", "teardown")):
        failure_category: str | None = None
        if report.failed:
            _, failure_category = collect_test_failure_artifacts(
                item, error_text=str(report.longrepr)
            )
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
        report.user_properties.append(("aegis_worker", worker_id))
        if failure_category is not None:
            report.user_properties.append(("aegis_failure_category", failure_category))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not _IS_CONTROLLER:
        return
    is_setup_skip = report.when == "setup" and report.skipped
    is_phase_failure = report.failed and report.when in ("setup", "teardown")
    if report.when != "call" and not is_setup_skip and not is_phase_failure:
        return

    props = dict(report.user_properties)
    worker = str(props.get("aegis_worker", "main"))
    raw_cat = props.get("aegis_failure_category")
    failure_category = str(raw_cat) if raw_cat is not None else None
    status: Literal["passed", "failed", "skipped", "error"]
    if report.skipped:
        status = "skipped"
    elif report.when in ("setup", "teardown") and report.failed:
        status = "error"
    elif report.passed:
        status = "passed"
    else:
        status = "failed"

    record = TestExecutionRecord(
        test_id=report.nodeid,
        run_id=RunContext.resolve_run_id(),
        status=status,
        duration_ms=round(report.duration * 1000.0, 2),
        browser=settings.BROWSER_NAME,
        environment=settings.ENVIRONMENT,
        git_sha=resolve_git_sha(),
        worker=worker,
        failure_category=failure_category,
    )

    prev_status = _RECORDED_NODES.get(report.nodeid)
    if prev_status is not None:
        if report.when == "teardown" and report.failed and prev_status == "passed":
            _RECORDED_NODES[report.nodeid] = "error"
            ReliabilityAnalyzer().upsert_execution(record)
        return

    _RECORDED_NODES[report.nodeid] = status
    ReliabilityAnalyzer().record_execution(record)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    if hasattr(session.config, "workerinput") or _is_collect_or_help(session.config):
        return
    started_at = getattr(session.config, "_aegis_started_at", datetime.now(UTC).isoformat())
    start_perf = getattr(session.config, "_aegis_start_perf", time.perf_counter())
    duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter:
        failed_ids = {
            r.nodeid for r in (reporter.stats.get("failed", []) + reporter.stats.get("error", []))
        }
        skipped_ids = {r.nodeid for r in reporter.stats.get("skipped", [])} - failed_ids
        passed_ids = {r.nodeid for r in reporter.stats.get("passed", [])} - failed_ids - skipped_ids
        passed = len(passed_ids)
        failed = len(failed_ids)
        skipped = len(skipped_ids)
    else:
        passed = failed = skipped = 0
    total = passed + failed + skipped

    workers = 1
    numprocesses = getattr(session.config.option, "numprocesses", None)
    if isinstance(numprocesses, int) and numprocesses > 0:
        workers = numprocesses

    run_ctx = RunContext()
    metadata = ExecutionMetadata(
        run_id=run_ctx.run_id,
        environment=settings.ENVIRONMENT,
        browser=settings.BROWSER_NAME,
        workers=workers,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        duration_ms=duration_ms,
        total_tests=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
    )
    metadata.save(run_ctx.metadata_path)
    if total > 0:
        ReliabilityAnalyzer().export_reports()
