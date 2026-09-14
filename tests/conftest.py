"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import http.server
import json
import os
import socketserver
import threading
import time
from collections.abc import Generator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from framework.api.auth_api import AuthAPI
from framework.api.cart_api import CartAPI
from framework.api.client import BaseAPIClient
from framework.api.orders_api import OrdersAPI
from framework.api.products_api import ProductsAPI
from framework.config.settings import settings
from framework.pages.storefront_page import StorefrontPage
from framework.utils.a11y_auditor import AccessibilityAuditor
from framework.utils.cdp_metrics import CDPTelemetryCollector
from framework.utils.chaos_network import ChaosNetworkInjector
from framework.utils.data_factory import DataFactory
from framework.utils.visual_differ import VisualDiffer

# ============================================================================
# Frontend HTTP Server (Serving ./frontend directory for UI tests)
# ============================================================================


class DualModeHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Serves files from the frontend directory with CORS headers and proper MIME types."""

    def __init__(self, *args, **kwargs):
        frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
        super().__init__(*args, directory=frontend_dir, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def log_message(self, format, *args):
        # Silence standard HTTP server access logs in pytest output
        pass


@pytest.fixture(scope="session", autouse=True)
def live_server():
    """Starts the frontend static server on an available port."""
    host = "127.0.0.1"

    server = socketserver.TCPServer((host, 0), DualModeHTTPHandler)
    server.allow_reuse_address = True
    assigned_port = server.server_address[1]

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    time.sleep(0.1)  # Brief pause to ensure socket is bound
    server_url = f"http://{host}:{assigned_port}"
    yield server_url
    server.shutdown()
    server.server_close()


# ============================================================================
# Playwright Browser and Context Lifecycle Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    browser_type = getattr(playwright_instance, settings.BROWSER_NAME)
    browser = browser_type.launch(
        headless=settings.HEADLESS,
        slow_mo=settings.SLOW_MO_MS,
    )
    yield browser
    browser.close()


@pytest.fixture(scope="function")
def context(browser: Browser) -> Generator[BrowserContext, None, None]:
    os.makedirs(settings.ARTIFACTS_DIR, exist_ok=True)
    ctx = browser.new_context(
        viewport={"width": settings.VIEWPORT_WIDTH, "height": settings.VIEWPORT_HEIGHT},
        record_video_dir=settings.ARTIFACTS_DIR if settings.CAPTURE_TRACE_ON_FAILURE else None,
    )
    ctx.set_default_timeout(settings.DEFAULT_TIMEOUT_MS)
    yield ctx
    ctx.close()


def _setup_default_browser_routes(p: Page) -> None:
    """Sets up deterministic mock routes for backend API calls when testing UI without live backend dependencies."""
    p.route(
        "**/api/v1/auth/login",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "token": "fast-track-login-token",
                        "user": {
                            "id": 101,
                            "name": "Customer User",
                            "email": "customer@example.com",
                            "role": "customer",
                        },
                    }
                ),
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    p.route(
        "**/api/v1/auth/register",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "token": "fast-track-register-token",
                        "user": {
                            "id": 102,
                            "name": "Registered Customer",
                            "email": "customer@example.com",
                            "role": "customer",
                        },
                    }
                ),
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    p.route(
        "**/api/v1/orders/checkout",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": 901,
                        "order_id": "ORD-771122",
                        "user_id": 42,
                        "status": "confirmed",
                        "total_amount": 161.99,
                        "items_count": 1,
                    }
                ),
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    p.route(
        "**/health",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"status": "healthy", "database": "healthy"}),
            )
            if route.request.method == "GET"
            else route.continue_()
        ),
    )
    p.route(
        "**/api/v1/products",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "data": [
                            {
                                "id": 1,
                                "name": "Apex Pro Mechanical Keyboard",
                                "category": "Electronics",
                                "price": 149.99,
                                "stock": 15,
                                "description": "Aircraft-grade aluminum frame, hot-swappable tactile switches, and PBT double-shot keycaps.",
                            },
                            {
                                "id": 2,
                                "name": "Precision Ergonomic Mouse",
                                "category": "Electronics",
                                "price": 79.99,
                                "stock": 24,
                                "description": "4000 DPI optical sensor, ultra-low latency wireless, and contoured thumb rest.",
                            },
                            {
                                "id": 3,
                                "name": "Studio Reference Headphones",
                                "category": "Audio",
                                "price": 249.99,
                                "stock": 8,
                                "description": "Open-back planar magnetic drivers delivering ultra-wide soundstage and neutral frequency response.",
                            },
                            {
                                "id": 4,
                                "name": "USB-C Braided Thunderbolt Cable",
                                "category": "Accessories",
                                "price": 29.99,
                                "stock": 50,
                                "description": "40Gbps data throughput and 100W Power Delivery with reinforced nylon braiding.",
                            },
                            {
                                "id": 5,
                                "name": "Solid Walnut Desk Mat (Extended)",
                                "category": "Workspace",
                                "price": 64.99,
                                "stock": 12,
                                "description": "Eco-friendly natural wool felt top with non-slip cork base and beveled edge detailing.",
                            },
                            {
                                "id": 6,
                                "name": "Ultra-Fast NVMe SSD Enclosure",
                                "category": "Electronics",
                                "price": 54.99,
                                "stock": 18,
                                "description": "Tool-free aluminum thermal enclosure supporting up to 10Gbps USB 3.2 Gen 2 transfer speeds.",
                            },
                        ],
                        "total": 6,
                        "page": 1,
                        "limit": 10,
                    }
                ),
            )
            if route.request.method == "GET"
            else route.continue_()
        ),
    )


@pytest.fixture(scope="function")
def page(context: BrowserContext, live_server: str) -> Generator[Page, None, None]:
    p = context.new_page()
    _setup_default_browser_routes(p)
    yield p
    p.close()


@pytest.fixture(scope="function")
def storefront_page(page: Page, live_server: str) -> StorefrontPage:
    sp = StorefrontPage(page, live_server)
    sp.open()
    return sp


# ============================================================================
# Fast-Track Pre-Authenticated Sessions (storageState pattern)
# ============================================================================


@pytest.fixture(scope="function")
def authenticated_page(context: BrowserContext, live_server: str) -> Generator[Page, None, None]:
    """Provides a Playwright page pre-authenticated as a customer without UI login overhead."""
    user_data = {
        "id": 42,
        "name": "Alex Taylor",
        "email": "customer@example.com",
        "role": "customer",
        "token": "fast-track-customer-jwt-token",
    }

    # Pre-inject authentication state into the browser context
    p = context.new_page()
    _setup_default_browser_routes(p)
    p.goto(live_server, wait_until="domcontentloaded")

    p.evaluate(
        """
        (user) => {
            localStorage.setItem('apex_user', JSON.stringify(user));
            document.cookie = `apex_token=${user.token}; path=/; max-age=86400; SameSite=Lax`;
            document.cookie = `apex_user=${encodeURIComponent(JSON.stringify(user))}; path=/; max-age=86400; SameSite=Lax`;
        }
    """,
        user_data,
    )

    p.reload(wait_until="domcontentloaded")
    yield p
    p.close()


@pytest.fixture(scope="function")
def admin_page(context: BrowserContext, live_server: str) -> Generator[Page, None, None]:
    """Provides a Playwright page pre-authenticated as an Admin with RBAC privileges."""
    admin_data = {
        "id": 1,
        "name": "System Admin",
        "email": "admin@example.com",
        "role": "admin",
        "token": "fast-track-admin-jwt-token",
    }

    p = context.new_page()
    _setup_default_browser_routes(p)
    p.goto(live_server, wait_until="domcontentloaded")

    p.evaluate(
        """
        (admin) => {
            localStorage.setItem('apex_user', JSON.stringify(admin));
            document.cookie = `apex_token=${admin.token}; path=/; max-age=86400; SameSite=Lax`;
            document.cookie = `apex_user=${encodeURIComponent(JSON.stringify(admin))}; path=/; max-age=86400; SameSite=Lax`;
        }
    """,
        admin_data,
    )

    p.reload(wait_until="domcontentloaded")
    yield p
    p.close()


# ============================================================================
# API Client Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def api_client() -> Generator[BaseAPIClient, None, None]:
    client = BaseAPIClient(base_url=settings.API_URL)
    yield client
    client.close()


@pytest.fixture(scope="function")
def auth_api(api_client: BaseAPIClient) -> AuthAPI:
    return AuthAPI(api_client)


@pytest.fixture(scope="function")
def products_api(api_client: BaseAPIClient) -> ProductsAPI:
    return ProductsAPI(api_client)


@pytest.fixture(scope="function")
def cart_api(api_client: BaseAPIClient) -> CartAPI:
    return CartAPI(api_client)


@pytest.fixture(scope="function")
def orders_api(api_client: BaseAPIClient) -> OrdersAPI:
    return OrdersAPI(api_client)


# ============================================================================
# Advanced SDET Utilities & Telemetry Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def data_factory() -> DataFactory:
    return DataFactory()


@pytest.fixture(scope="function")
def cdp_collector(page: Page) -> CDPTelemetryCollector:
    return CDPTelemetryCollector(page)


@pytest.fixture(scope="function")
def chaos_injector(page: Page) -> Generator[ChaosNetworkInjector, None, None]:
    injector = ChaosNetworkInjector(page)
    yield injector
    injector.clear_faults()


@pytest.fixture(scope="function")
def axe_auditor(page: Page) -> AccessibilityAuditor:
    return AccessibilityAuditor(page)


@pytest.fixture(scope="session")
def visual_checker() -> VisualDiffer:
    return VisualDiffer()


# ============================================================================
# Pytest Hooks: Automatic Failure Screenshots and Reporting
# ============================================================================


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed and settings.CAPTURE_SCREENSHOT_ON_FAILURE:
        page_instance = (
            item.funcargs.get("page")
            or item.funcargs.get("authenticated_page")
            or item.funcargs.get("admin_page")
        )
        if page_instance:
            try:
                os.makedirs(settings.ARTIFACTS_DIR, exist_ok=True)
                screenshot_path = os.path.join(settings.ARTIFACTS_DIR, f"fail_{item.name}.png")
                png_bytes = page_instance.screenshot(path=screenshot_path, full_page=True)
                try:
                    import allure

                    allure.attach(
                        png_bytes,
                        name=f"Failure Screenshot ({item.name})",
                        attachment_type=allure.attachment_type.PNG,
                    )
                except (ImportError, RuntimeError, TypeError, AttributeError):
                    pass
            except (OSError, RuntimeError):
                pass
