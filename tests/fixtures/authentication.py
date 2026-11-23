"""Authentication session fixtures for mocked UI and live integration testing."""

import json
from collections.abc import Generator
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Page

from framework.api.auth_api import AuthAPI
from framework.api.models.auth_models import UserLoginRequest
from framework.artifacts.collectors import BrowserConsoleCollector, NetworkFailureCollector
from framework.artifacts.manager import ArtifactManager
from framework.config.settings import settings
from framework.data.manager import TestDataManager
from tests.support.mock_routes import setup_default_browser_routes


def _inject_browser_session(page: Page, live_server: str, user_session: dict[str, Any]) -> None:
    """Populate localStorage and cookies with the session DTO and reload the app."""
    page.goto(live_server, wait_until="domcontentloaded")
    page.evaluate(
        """
        (user) => {
            const serialized = JSON.stringify(user);
            localStorage.setItem('aegis_user', serialized);
            document.cookie = `aegis_token=${user.token}; path=/; max-age=86400; SameSite=Lax`;
        }
        """,
        user_session,
    )
    page.reload(wait_until="domcontentloaded")


@pytest.fixture(scope="function")
def mocked_authenticated_page(
    context: BrowserContext,
    live_server: str,
    artifact_manager: ArtifactManager,
    console_collector: BrowserConsoleCollector,
    network_collector: NetworkFailureCollector,
) -> Generator[Page, None, None]:
    """Provide a mocked Playwright page pre-authenticated as a customer."""
    user_data = {
        "id": 42,
        "name": "Alex Taylor",
        "email": "customer@example.com",
        "role": "customer",
        "token": "fast-track-customer-jwt-token",
    }
    p = context.new_page()
    console_collector.attach(p)
    network_collector.attach(p)
    setup_default_browser_routes(p)
    try:
        _inject_browser_session(p, live_server, user_data)
        yield p
    finally:
        p.close()
        artifact_manager.finalize_page_video(p)


@pytest.fixture(scope="function")
def mocked_admin_page(
    context: BrowserContext,
    live_server: str,
    artifact_manager: ArtifactManager,
    console_collector: BrowserConsoleCollector,
    network_collector: NetworkFailureCollector,
) -> Generator[Page, None, None]:
    """Provide a mocked Playwright page pre-authenticated as an Admin."""
    admin_data = {
        "id": 1,
        "name": "System Admin",
        "email": "admin@example.com",
        "role": "admin",
        "token": "fast-track-admin-jwt-token",
    }
    p = context.new_page()
    console_collector.attach(p)
    network_collector.attach(p)
    setup_default_browser_routes(p)
    try:
        _inject_browser_session(p, live_server, admin_data)
        yield p
    finally:
        p.close()
        artifact_manager.finalize_page_video(p)


@pytest.fixture(scope="function")
def authenticated_page(
    context: BrowserContext,
    live_server: str,
    artifact_manager: ArtifactManager,
    auth_api: AuthAPI,
    test_data_manager: TestDataManager,
    backend_health: dict[str, str],
    console_collector: BrowserConsoleCollector,
    network_collector: NetworkFailureCollector,
) -> Generator[Page, None, None]:
    """Register a unique customer via the live Go API and inject the real JWT session."""
    del backend_health
    user = test_data_manager.create_isolated_user("customer")
    auth_api.client.set_token(user.token)
    session_user = {
        "id": user.user_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "token": user.token,
    }

    context.add_init_script(f"window.AEGIS_API_URL = {json.dumps(settings.API_URL)};")
    p = context.new_page()
    console_collector.attach(p)
    network_collector.attach(p)
    try:
        _inject_browser_session(p, live_server, session_user)
        yield p
    finally:
        p.close()
        artifact_manager.finalize_page_video(p)


@pytest.fixture(scope="function")
def admin_page(
    context: BrowserContext,
    live_server: str,
    artifact_manager: ArtifactManager,
    auth_api: AuthAPI,
    backend_health: dict[str, str],
    console_collector: BrowserConsoleCollector,
    network_collector: NetworkFailureCollector,
) -> Generator[Page, None, None]:
    """Authenticate as Admin via the live Go API and inject the real admin JWT session."""
    del backend_health
    login_res = auth_api.login(
        UserLoginRequest(
            email=settings.ADMIN_EMAIL,
            password=settings.ADMIN_PASSWORD,
        )
    )
    assert login_res.status_code == 200, f"Admin login failed: {login_res.text}"
    payload = login_res.json()
    session_user = {**payload["user"], "token": payload["token"]}

    context.add_init_script(f"window.AEGIS_API_URL = {json.dumps(settings.API_URL)};")
    p = context.new_page()
    console_collector.attach(p)
    network_collector.attach(p)
    try:
        _inject_browser_session(p, live_server, session_user)
        yield p
    finally:
        p.close()
        artifact_manager.finalize_page_video(p)
