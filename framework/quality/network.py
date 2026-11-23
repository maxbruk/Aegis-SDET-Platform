"""Network fault injection utility for resilience testing."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, Route


class ChaosNetworkInjector:
    """Simulates real-world network degradations, latency storms, and HTTP server failures."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self._registered_routes: list[tuple[str, Callable[[Route], None]]] = []

    def inject_latency(self, url_pattern: str, delay_seconds: float) -> None:
        """Inject artificial latency into matched requests."""

        def handle_route(route: Route) -> None:
            time.sleep(delay_seconds)
            route.fallback()

        self.page.route(url_pattern, handle_route)
        self._registered_routes.append((url_pattern, handle_route))

    def inject_http_error(
        self,
        url_pattern: str,
        status_code: int = 500,
        error_json: dict[str, Any] | None = None,
    ) -> None:
        """Fail matching requests with a simulated HTTP status code."""
        body = json.dumps(error_json or {"error": "Simulated Chaos Failure", "status": status_code})

        def handle_route(route: Route) -> None:
            route.fulfill(
                status=status_code,
                headers={"Content-Type": "application/json"},
                body=body,
            )

        self.page.route(url_pattern, handle_route)
        self._registered_routes.append((url_pattern, handle_route))

    def inject_rate_limit(self, url_pattern: str, retry_after: int = 5) -> None:
        """Simulate HTTP 429 Too Many Requests rate limiting."""

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
        self._registered_routes.append((url_pattern, handle_route))

    def set_offline_mode(self, offline: bool = True) -> None:
        """Simulate complete network disconnection in the browser context."""
        self.page.context.set_offline(offline)

    def clear_faults(self, url_pattern: str | None = None) -> None:
        """Unroute only injected chaos handlers and restore online state."""
        remaining: list[tuple[str, Callable[[Route], None]]] = []
        for pattern, handler in self._registered_routes:
            if url_pattern is None or pattern == url_pattern:
                self.page.unroute(pattern, handler)
            else:
                remaining.append((pattern, handler))
        self._registered_routes = remaining
        self.page.context.set_offline(False)
