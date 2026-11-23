"""Full-stack End-to-End tests spanning Storefront UI, Go REST Backend, and PostgreSQL."""

import allure
import pytest
from playwright.sync_api import Page, expect

from framework.api.orders_api import OrdersAPI
from framework.data.manager import TestDataManager
from framework.pages.storefront_page import StorefrontPage
from framework.utils.data_factory import DataFactory


@allure.epic("Full-Stack E2E")
@allure.feature("Storefront UI + Go Backend + PostgreSQL")
@pytest.mark.e2e
class TestFullStackE2E:
    """End-to-End tests executed without route mocks against real backend services."""

    def test_real_storefront_live_api_status_and_catalog(
        self,
        integration_storefront_page: StorefrontPage,
    ) -> None:
        """Verify Storefront connects to the live Go backend and renders PostgreSQL products."""
        status_label = integration_storefront_page.page.locator("#api-status-label")
        expect(status_label).to_have_text("API Live", timeout=5000)

        cards = integration_storefront_page.get_product_cards()
        assert len(cards) >= 6

    def test_real_authenticated_customer_checkout_e2e(
        self,
        authenticated_page: Page,
        live_server: str,
        orders_api: OrdersAPI,
        test_data_manager: TestDataManager,
        data_factory: DataFactory,
    ) -> None:
        """Complete checkout on an isolated product and verify order persistence in PostgreSQL."""
        isolated = test_data_manager.create_isolated_product(price=39.99, stock=15)
        storefront = StorefrontPage(authenticated_page, live_server)
        expect(authenticated_page.locator("#api-status-label")).to_have_text(
            "API Live", timeout=5000
        )

        # Wait for live polling sync to render the newly provisioned isolated product
        product = storefront.get_product_card_by_id(isolated.product_id)
        expect(product.root).to_be_visible(timeout=8000)
        product.add_to_cart()
        expect(storefront.header.cart_count_badge).to_have_text("1")

        storefront.header.open_cart()
        expect(storefront.cart_drawer.drawer_container).to_be_visible()
        storefront.cart_drawer.proceed_to_checkout()

        expect(storefront.checkout_modal.modal).to_be_visible()
        storefront.checkout_modal.fill_address(data_factory.random_address())
        idem_key = storefront.checkout_modal.get_idempotency_key()
        assert idem_key.startswith("idem-")

        storefront.checkout_modal.submit_order()
        expect(storefront.checkout_modal.success_view).to_be_visible()
        order_id = storefront.checkout_modal.get_confirmed_order_id()
        assert order_id.startswith("ORD-")

        orders_res = orders_api.get_orders()
        assert orders_res.status_code == 200, orders_res.text
        orders = orders_res.json()["orders"]
        matching = [o for o in orders if o["order_id"] == order_id]
        assert len(matching) == 1
        assert matching[0]["idempotency_key"] == idem_key

        detail_res = orders_api.get_order(int(matching[0]["id"]))
        assert detail_res.status_code == 200, detail_res.text
        assert detail_res.json()["order_id"] == order_id
        test_data_manager.register_order_for_cleanup(int(matching[0]["id"]))
