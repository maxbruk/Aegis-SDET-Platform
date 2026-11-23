"""Playwright browser, context, and mode-separated page fixtures."""

import json
import os
from collections.abc import Generator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from framework.artifacts.collectors import BrowserConsoleCollector, NetworkFailureCollector
from framework.artifacts.manager import ArtifactManager
from framework.config.settings import settings
from framework.execution.run_context import RunContext
from framework.pages.storefront_page import StorefrontPage
from tests.support.mock_routes import setup_default_browser_routes


@pytest.fixture(scope="session")
def run_context() -> RunContext:
    ctx = RunContext()
    ctx.ensure_directories()
    return ctx


@pytest.fixture(scope="session")
def artifact_manager(run_context: RunContext) -> ArtifactManager:
    run_context.ensure_directories()
    return ArtifactManager(run_context=run_context)


@pytest.fixture(scope="function")
def console_collector() -> BrowserConsoleCollector:
    return BrowserConsoleCollector()


@pytest.fixture(scope="function")
def network_collector() -> NetworkFailureCollector:
    return NetworkFailureCollector()


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    browser_type = getattr(playwright_instance, settings.BROWSER_NAME)
    browser_instance = browser_type.launch(
        headless=settings.HEADLESS,
        slow_mo=settings.SLOW_MO_MS,
    )
    try:
        yield browser_instance
    finally:
        browser_instance.close()


@pytest.fixture(scope="function")
def context(
    browser: Browser,
    artifact_manager: ArtifactManager,
) -> Generator[BrowserContext, None, None]:
    os.makedirs(settings.ARTIFACTS_DIR, exist_ok=True)
    video_dir = (
        str(artifact_manager.run_context.videos_dir) if settings.CAPTURE_VIDEO_ON_FAILURE else None
    )
    ctx = browser.new_context(
        viewport={"width": settings.VIEWPORT_WIDTH, "height": settings.VIEWPORT_HEIGHT},
        record_video_dir=video_dir,
    )
    ctx.set_default_timeout(settings.DEFAULT_TIMEOUT_MS)
    artifact_manager.start_tracing(ctx)
    try:
        yield ctx
    finally:
        artifact_manager.stop_tracing(ctx)
        ctx.close()


@pytest.fixture(scope="function")
def mocked_page(
    context: BrowserContext,
    artifact_manager: ArtifactManager,
    console_collector: BrowserConsoleCollector,
    network_collector: NetworkFailureCollector,
) -> Generator[Page, None, None]:
    """Provide a Playwright page with deterministic mocked backend API routes."""
    p = context.new_page()
    console_collector.attach(p)
    network_collector.attach(p)
    setup_default_browser_routes(p)
    try:
        yield p
    finally:
        p.close()
        artifact_manager.finalize_page_video(p)


@pytest.fixture(scope="function")
def mocked_storefront_page(mocked_page: Page, live_server: str) -> StorefrontPage:
    """Open StorefrontPage in deterministic mocked-backend mode."""
    sp = StorefrontPage(mocked_page, live_server)
    sp.open()
    return sp


@pytest.fixture(scope="function")
def integration_page(
    context: BrowserContext,
    artifact_manager: ArtifactManager,
    backend_health: dict[str, str],
    console_collector: BrowserConsoleCollector,
    network_collector: NetworkFailureCollector,
) -> Generator[Page, None, None]:
    """Provide a clean Playwright page wired directly to the live Go backend."""
    del backend_health
    context.add_init_script(f"window.AEGIS_API_URL = {json.dumps(settings.API_URL)};")
    p = context.new_page()
    console_collector.attach(p)
    network_collector.attach(p)
    try:
        yield p
    finally:
        p.close()
        artifact_manager.finalize_page_video(p)


@pytest.fixture(scope="function")
def integration_storefront_page(
    integration_page: Page,
    live_server: str,
) -> StorefrontPage:
    """Open StorefrontPage connected to the live Go backend and PostgreSQL."""
    sp = StorefrontPage(integration_page, live_server)
    sp.open()
    return sp


@pytest.fixture(scope="function")
def page(mocked_page: Page) -> Page:
    """Default page alias for non-integration suites (resilience, performance, visual, a11y)."""
    return mocked_page


@pytest.fixture(scope="function")
def storefront_page(mocked_storefront_page: StorefrontPage) -> StorefrontPage:
    """Default storefront_page alias for mocked UI and quality-analysis suites."""
    return mocked_storefront_page
