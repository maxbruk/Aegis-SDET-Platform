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
from playwright.sync_api import Page, expect

from framework.pages.storefront_page import StorefrontPage
from framework.utils.data_factory import DataFactory


@allure.epic("Order Checkout")
@allure.feature("End-to-End Customer Checkout Journey")
@pytest.mark.ui
@pytest.mark.smoke
class TestCheckoutE2E:
    """Full End-to-End customer purchase funnel tests."""

    @allure.story("Full Customer Checkout Journey with Idempotency Key")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_full_customer_checkout_journey(
        self,
        authenticated_page: Page,
        live_server: str,
        data_factory: DataFactory,
    ):
        """Exercises complete journey: browse -> add item -> open drawer -> checkout -> place order -> confirmation."""
        storefront = StorefrontPage(authenticated_page, live_server)

        with allure.step("Step 1: Add product to cart"):
            product = storefront.get_product_card_by_id(1)
            product.add_to_cart()
            expect(storefront.header.cart_count_badge).to_have_text("1")

        with allure.step("Step 2: Open cart drawer and proceed to checkout"):
            storefront.header.open_cart()
            expect(storefront.cart_drawer.drawer_container).to_be_visible()
            storefront.cart_drawer.proceed_to_checkout()

        with allure.step("Step 3: Fill checkout address and verify Idempotency-Key"):
            expect(storefront.checkout_modal.modal).to_be_visible()
            address = data_factory.random_address()
            storefront.checkout_modal.fill_address(address)
            idem_key = storefront.checkout_modal.get_idempotency_key()
            assert idem_key.startswith("idem-")

        with allure.step("Step 4: Submit order"):
            storefront.checkout_modal.submit_order()

        with allure.step("Step 5: Verify Order Confirmation & Reference ID"):
            expect(storefront.checkout_modal.success_view).to_be_visible()
            order_id = storefront.checkout_modal.get_confirmed_order_id()
            assert order_id.startswith("ORD-")
            assert len(order_id) > 6
