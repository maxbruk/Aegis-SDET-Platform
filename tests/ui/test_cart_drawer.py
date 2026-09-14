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
class TestCartDrawer:
    """Tests slide-over Cart Drawer, quantity changes, line item deletion, and subtotal calculations."""

    @allure.story("Add Product to Cart & Open Drawer")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_add_product_to_cart_and_open_drawer(self, storefront_page: StorefrontPage):
        """Adds product to cart, asserts badge increments, and verifies drawer items."""
        with allure.step("Add first product card to cart"):
            cards = storefront_page.get_product_cards()
            first_card = cards[0]
            item_title = first_card.get_title_text()
            item_price = first_card.get_price_value()
            assert len(item_title) > 0

            first_card.add_to_cart()
            expect(storefront_page.header.cart_count_badge).to_have_text("1")

        with allure.step("Open cart drawer and assert line item details"):
            storefront_page.header.open_cart()
            expect(storefront_page.cart_drawer.drawer_container).to_be_visible()

            items = storefront_page.cart_drawer.get_cart_items()
            assert len(items) == 1
            assert items[0].get_quantity() == 1

            subtotal, _tax, total = storefront_page.cart_drawer.get_totals()
            assert subtotal == item_price
            assert total > subtotal

    @allure.story("Quantity Stepper Increment & Decrement")
    @allure.severity(allure.severity_level.NORMAL)
    def test_quantity_stepper_increment_and_decrement(self, storefront_page: StorefrontPage):
        """Increments quantity to 2, asserts updated total, then decrements back to 1."""
        with allure.step("Add product and open drawer"):
            cards = storefront_page.get_product_cards()
            cards[0].add_to_cart()
            storefront_page.header.open_cart()

        with allure.step("Increment quantity to 2"):
            item = storefront_page.cart_drawer.get_cart_items()[0]
            item.increment_quantity()
            assert item.get_quantity() == 2
            expect(storefront_page.header.cart_count_badge).to_have_text("2")

        with allure.step("Decrement quantity back to 1"):
            item.decrement_quantity()
            assert item.get_quantity() == 1
            expect(storefront_page.header.cart_count_badge).to_have_text("1")

    @allure.story("Remove Line Item from Cart")
    @allure.severity(allure.severity_level.NORMAL)
    def test_remove_item_from_cart(self, storefront_page: StorefrontPage):
        """Removes single item from cart drawer and asserts empty state."""
        with allure.step("Add product and remove via delete button"):
            cards = storefront_page.get_product_cards()
            cards[0].add_to_cart()
            storefront_page.header.open_cart()

            item = storefront_page.cart_drawer.get_cart_items()[0]
            item.remove()

        with allure.step("Assert cart is empty"):
            expect(storefront_page.cart_drawer.empty_view).to_be_visible()
            expect(storefront_page.header.cart_count_badge).to_have_text("0")

    @allure.story("Clear All Cart Items")
    @allure.severity(allure.severity_level.NORMAL)
    def test_clear_all_items_button(self, storefront_page: StorefrontPage):
        """Adds multiple products and clicks 'Clear All' button."""
        with allure.step("Add multiple items to cart"):
            cards = storefront_page.get_product_cards()
            cards[0].add_to_cart()
            cards[1].add_to_cart()
            storefront_page.header.open_cart()

        with allure.step("Clear cart via clear button"):
            storefront_page.cart_drawer.clear_cart()
            expect(storefront_page.cart_drawer.empty_view).to_be_visible()
            expect(storefront_page.header.cart_count_badge).to_have_text("0")
