"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import time

from playwright.sync_api import Page


class BasePage:
    """Base Page Object providing resilient waiting, navigation, and screenshot mechanisms."""

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")

    def navigate(self, path: str = "") -> None:
        """Navigates to the specified relative or absolute URL path."""
        target_url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        self.page.goto(target_url, wait_until="domcontentloaded")

    def wait_for_dom_ready(self, timeout: float = 10000) -> None:
        """Wait for DOM content loaded and network idle."""
        self.page.wait_for_load_state("domcontentloaded", timeout=timeout)

    def reload(self) -> None:
        """Reload the current page."""
        self.page.reload(wait_until="domcontentloaded")

    def get_title(self) -> str:
        """Return the current document title."""
        return self.page.title()

    def get_url(self) -> str:
        """Return the current URL."""
        return self.page.url

    def take_screenshot(self, name: str | None = None) -> bytes:
        """Capture full-page screenshot for debugging or visual comparison."""
        filename = f"screenshot_{int(time.time())}.png" if not name else f"{name}.png"
        return self.page.screenshot(path=f"reports/artifacts/{filename}", full_page=True)

    def evaluate_js(self, script: str) -> any:
        """Evaluate custom JavaScript in the browser context."""
        return self.page.evaluate(script)
