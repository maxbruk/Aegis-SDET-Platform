"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from playwright.sync_api import Locator, Page


class ToastComponent:
    """Encapsulates floating toast notification assertions."""

    def __init__(self, page: Page):
        self.page = page
        self.container: Locator = page.locator('[data-testid="toast-container"]')
        self.toasts: Locator = page.locator('[data-testid="toast"]')

    def get_latest_toast_text(self) -> str:
        self.toasts.first.wait_for(state="visible", timeout=5000)
        return self.toasts.first.inner_text()

    def wait_for_toast(self, expected_text: str, timeout: float = 5000) -> None:
        self.page.locator(f'[data-testid="toast"]:has-text("{expected_text}")').wait_for(
            state="visible", timeout=timeout
        )
