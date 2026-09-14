"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import json
import time
from typing import Any

from playwright.sync_api import Page, Route


class ChaosNetworkInjector:
    """Simulates real-world network degradations, latency storms, and HTTP server failures."""

    def __init__(self, page: Page):
        self.page = page

    def inject_latency(self, url_pattern: str, delay_seconds: float) -> None:
        """Injects artificial latency into matched requests."""

        def handle_route(route: Route) -> None:
            time.sleep(delay_seconds)
            route.continue_()

        self.page.route(url_pattern, handle_route)

    def inject_http_error(
        self,
        url_pattern: str,
        status_code: int = 500,
        error_json: dict[str, Any] | None = None,
    ) -> None:
        """Fails matching requests with a simulated HTTP status code."""
        body = json.dumps(error_json or {"error": "Simulated Chaos Failure", "status": status_code})

        def handle_route(route: Route) -> None:
            route.fulfill(
                status=status_code,
                headers={"Content-Type": "application/json"},
                body=body,
            )

        self.page.route(url_pattern, handle_route)

    def inject_rate_limit(self, url_pattern: str, retry_after: int = 5) -> None:
        """Simulates HTTP 429 Too Many Requests rate limiting."""

        def handle_route(route: Route) -> None:
            route.fulfill(
                status=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(retry_after),
                },
                body=json.dumps(
                    {"error": "Rate limit exceeded. Please slow down.", "code": "RATE_LIMIT"}
                ),
            )

        self.page.route(url_pattern, handle_route)

    def set_offline_mode(self, offline: bool = True) -> None:
        """Simulates complete network disconnection in the browser context."""
        self.page.context.set_offline(offline)

    def clear_faults(self, url_pattern: str | None = None) -> None:
        """Unroutes faults."""
        if url_pattern:
            self.page.unroute(url_pattern)
        else:
            self.page.unroute_all()
            self.page.context.set_offline(False)
