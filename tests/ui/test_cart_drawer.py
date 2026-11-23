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


@allure.epic("Shopping Cart")
@allure.feature("Cart Drawer & Item Manipulation")
@pytest.mark.ui
@pytest.mark.ui_mocked
class TestCartDrawer:
    """Tests slide-over Cart Drawer, quantity changes, line item deletion, and subtotal calculations."""

    @allure.story("Add Product to Cart & Open Drawer")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_add_product_to_cart_and_open_drawer(self, mocked_storefront_page: StorefrontPage):
        """Adds product to cart, asserts badge increments, and verifies drawer items."""
        with allure.step("Add first product card to cart"):
            cards = mocked_storefront_page.get_product_cards()
            first_card = cards[0]
            item_title = first_card.get_title_text()
            item_price = first_card.get_price_value()
            assert len(item_title) > 0

            first_card.add_to_cart()
            expect(mocked_storefront_page.header.cart_count_badge).to_have_text("1")

        with allure.step("Open cart drawer and assert line item details"):
            mocked_storefront_page.header.open_cart()
            expect(mocked_storefront_page.cart_drawer.drawer_container).to_be_visible()

            items = mocked_storefront_page.cart_drawer.get_cart_items()
            assert len(items) == 1
            assert items[0].get_quantity() == 1

            subtotal, _tax, total = mocked_storefront_page.cart_drawer.get_totals()
            assert subtotal == item_price
            assert total > subtotal

    @allure.story("Quantity Stepper Increment & Decrement")
    @allure.severity(allure.severity_level.NORMAL)
    def test_quantity_stepper_increment_and_decrement(self, mocked_storefront_page: StorefrontPage):
        """Increments quantity to 2, asserts updated total, then decrements back to 1."""
        with allure.step("Add product and open drawer"):
            cards = mocked_storefront_page.get_product_cards()
            cards[0].add_to_cart()
            mocked_storefront_page.header.open_cart()

        with allure.step("Increment quantity to 2"):
            item = mocked_storefront_page.cart_drawer.get_cart_items()[0]
            item.increment_quantity()
            assert item.get_quantity() == 2
            expect(mocked_storefront_page.header.cart_count_badge).to_have_text("2")

        with allure.step("Decrement quantity back to 1"):
            item.decrement_quantity()
            assert item.get_quantity() == 1
            expect(mocked_storefront_page.header.cart_count_badge).to_have_text("1")

    @allure.story("Remove Line Item from Cart")
    @allure.severity(allure.severity_level.NORMAL)
    def test_remove_item_from_cart(self, mocked_storefront_page: StorefrontPage):
        """Removes single item from cart drawer and asserts empty state."""
        with allure.step("Add product and remove via delete button"):
            cards = mocked_storefront_page.get_product_cards()
            cards[0].add_to_cart()
            mocked_storefront_page.header.open_cart()

            item = mocked_storefront_page.cart_drawer.get_cart_items()[0]
            item.remove()

        with allure.step("Assert cart is empty"):
            expect(mocked_storefront_page.cart_drawer.empty_view).to_be_visible()
            expect(mocked_storefront_page.header.cart_count_badge).to_have_text("0")

    @allure.story("Clear All Cart Items")
    @allure.severity(allure.severity_level.NORMAL)
    def test_clear_all_items_button(self, mocked_storefront_page: StorefrontPage):
        """Adds multiple products and clicks 'Clear All' button."""
        with allure.step("Add multiple items to cart"):
            cards = mocked_storefront_page.get_product_cards()
            cards[0].add_to_cart()
            cards[1].add_to_cart()
            mocked_storefront_page.header.open_cart()

        with allure.step("Clear cart via clear button"):
            mocked_storefront_page.cart_drawer.clear_cart()
            expect(mocked_storefront_page.cart_drawer.empty_view).to_be_visible()
            expect(mocked_storefront_page.header.cart_count_badge).to_have_text("0")
