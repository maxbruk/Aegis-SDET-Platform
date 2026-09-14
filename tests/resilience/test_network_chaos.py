"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import allure
import pytest
from playwright.sync_api import expect

from framework.pages.storefront_page import StorefrontPage
from framework.utils.chaos_network import ChaosNetworkInjector


@allure.epic("Resilience & Chaos Engineering")
@allure.feature("Network Fault Injection & Error Resilience")
@pytest.mark.resilience
class TestNetworkChaos:
    """Simulates real-world network failures (500, 429, latency, offline) via Playwright route interception."""

    @allure.story("Server HTTP 500 Fault on Checkout")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_simulated_500_internal_server_error_on_checkout(
        self,
        storefront_page: StorefrontPage,
        chaos_injector: ChaosNetworkInjector,
    ):
        """Intercepts /orders/checkout and responds with HTTP 500 error, ensuring UI displays error banner."""
        with allure.step("Add product to cart"):
            product = storefront_page.get_product_card_by_id(1)
            product.add_to_cart()

        with allure.step("Inject HTTP 500 fault into /api/v1/orders/checkout"):
            chaos_injector.inject_http_error(
                "**/api/v1/orders/checkout",
                status_code=500,
                error_json={"error": "ACID Transaction Failed: Database lock contention timeout"},
            )

        with allure.step("Attempt checkout submission"):
            storefront_page.header.open_cart()
            storefront_page.cart_drawer.proceed_to_checkout()
            storefront_page.checkout_modal.fill_address("1 Infinite Loop, Cupertino, CA")
            storefront_page.checkout_modal.submit_order()

        with allure.step("Assert error banner appears without crash"):
            expect(storefront_page.checkout_modal.error_banner).to_be_visible()

    @allure.story("HTTP 429 Rate Limiting Backoff")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_simulated_429_rate_limiting(
        self,
        storefront_page: StorefrontPage,
        chaos_injector: ChaosNetworkInjector,
    ):
        """Intercepts login and returns 429 Too Many Requests."""
        with allure.step("Inject HTTP 429 rate limit into /api/v1/auth/login"):
            chaos_injector.inject_rate_limit("**/api/v1/auth/login", retry_after=10)

        with allure.step("Attempt login submission"):
            storefront_page.header.open_auth_modal()
            storefront_page.auth_modal.login("test@example.com", "Password123!")

        with allure.step("Assert rate limit error banner is displayed"):
            expect(storefront_page.auth_modal.error_banner).to_be_visible()

    @allure.story("Browser Offline Network Mode")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_browser_offline_network_mode(
        self,
        storefront_page: StorefrontPage,
        chaos_injector: ChaosNetworkInjector,
    ):
        """Emulates offline network connectivity and asserts offline banner visibility."""
        with allure.step("Simulate browser offline transition"):
            chaos_injector.set_offline_mode(True)
            storefront_page.evaluate_js("window.dispatchEvent(new Event('offline'))")

        with allure.step("Assert offline warning banner is displayed"):
            expect(storefront_page.offline_banner).to_be_visible()

        with allure.step("Restore online mode and assert banner hides"):
            chaos_injector.set_offline_mode(False)
            storefront_page.evaluate_js("window.dispatchEvent(new Event('online'))")
            expect(storefront_page.offline_banner).to_be_hidden()
