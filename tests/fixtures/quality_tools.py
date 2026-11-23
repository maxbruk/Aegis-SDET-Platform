"""Quality analysis, telemetry, chaos, visual, and test-data fixtures."""

from collections.abc import Generator

import pytest
from playwright.sync_api import Page

from framework.data.manager import TestDataManager
from framework.execution.run_context import RunContext
from framework.quality.accessibility import AccessibilityAuditor
from framework.quality.network import ChaosNetworkInjector
from framework.quality.visual import VisualDiffer
from framework.telemetry.performance import CDPTelemetryCollector
from framework.utils.data_factory import DataFactory


@pytest.fixture(scope="session")
def data_factory() -> DataFactory:
    return DataFactory()


@pytest.fixture(scope="function")
def test_data_manager(run_context: RunContext) -> Generator[TestDataManager, None, None]:
    """Provision isolated per-test entities and guarantee cleanup even after test failures."""
    manager = TestDataManager(run_context=run_context)
    try:
        yield manager
    finally:
        manager.cleanup()


@pytest.fixture(scope="function")
def cdp_collector(page: Page) -> CDPTelemetryCollector:
    return CDPTelemetryCollector(page)


@pytest.fixture(scope="function")
def chaos_injector(page: Page) -> Generator[ChaosNetworkInjector, None, None]:
    injector = ChaosNetworkInjector(page)
    try:
        yield injector
    finally:
        injector.clear_faults()


@pytest.fixture(scope="function")
def axe_auditor(page: Page) -> AccessibilityAuditor:
    return AccessibilityAuditor(page)


@pytest.fixture(scope="session")
def visual_checker() -> VisualDiffer:
    return VisualDiffer()
