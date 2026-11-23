"""Browser runtime snapshot helpers via Playwright and CDP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page


def collect_browser_runtime_snapshot(page: Page) -> dict[str, Any]:
    """Collect document readiness, viewport dimensions, and resource counts from a page."""
    return page.evaluate(
        """
        () => ({
            url: window.location.href,
            readyState: document.readyState,
            viewport: { width: window.innerWidth, height: window.innerHeight },
            dpr: window.devicePixelRatio || 1,
            domNodes: document.querySelectorAll('*').length,
            resourcesCount: performance.getEntriesByType('resource').length
        })
        """
    )
