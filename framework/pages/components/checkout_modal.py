"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from playwright.sync_api import Locator, Page


class CheckoutModalComponent:
    """Encapsulates the Checkout Modal dialog and Order Confirmation state."""

    def __init__(self, page: Page):
        self.page = page
        self.modal: Locator = page.locator('[data-testid="checkout-modal"]')
        self.close_btn: Locator = page.locator('[data-testid="checkout-close-btn"]')

        # Form Elements
        self.form_view: Locator = page.locator("#checkout-form-view")
        self.name_input: Locator = page.locator('[data-testid="checkout-name"]')
        self.email_input: Locator = page.locator('[data-testid="checkout-email"]')
        self.address_input: Locator = page.locator('[data-testid="checkout-address"]')
        self.idempotency_key_display: Locator = page.locator(
            '[data-testid="idempotency-key-display"]'
        )
        self.place_order_btn: Locator = page.locator('[data-testid="place-order-btn"]')
        self.error_banner: Locator = page.locator('[data-testid="checkout-error-banner"]')

        # Order Confirmation Elements
        self.success_card: Locator = page.locator('[data-testid="order-success-card"]')
        self.success_view: Locator = self.success_card
        self.confirmed_order_id: Locator = page.locator('[data-testid="confirmed-order-id"]')
        self.confirmed_order_status: Locator = page.locator(
            '[data-testid="confirmed-order-status"]'
        )
        self.confirmed_order_total: Locator = page.locator('[data-testid="confirmed-order-total"]')
        self.confirmed_idempotency_key: Locator = page.locator(
            '[data-testid="confirmed-idempotency-key"]'
        )
        self.continue_shopping_btn: Locator = page.locator(
            '[data-testid="order-success-continue-btn"]'
        )

    def is_visible(self) -> bool:
        return self.modal.is_visible()

    def fill_customer_info(self, name: str, email: str, address: str) -> None:
        self.name_input.fill(name)
        self.email_input.fill(email)
        self.address_input.fill(address)

    def fill_address(
        self, address: str, name: str = "Alex Taylor", email: str = "customer@example.com"
    ) -> None:
        self.fill_customer_info(name, email, address)

    def get_idempotency_key(self) -> str:
        return self.idempotency_key_display.inner_text().strip()

    def get_confirmed_order_id(self) -> str:
        return self.confirmed_order_id.inner_text().strip()

    def submit_order(self) -> None:
        self.place_order_btn.click()

    def close(self) -> None:
        self.close_btn.click()

    def continue_shopping(self) -> None:
        self.continue_shopping_btn.click()
