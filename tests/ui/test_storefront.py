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


@allure.epic("Storefront & Catalog")
@allure.feature("Product Catalog Browsing & Search")
@pytest.mark.ui
class TestStorefrontCatalog:
    """End-to-End tests for Storefront browsing, filtering, and searching."""

    @allure.story("Default Catalog Hydration")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_catalog_loads_default_products(self, storefront_page: StorefrontPage):
        """Verifies that the catalog initially loads default inventory items."""
        with allure.step("Verify default product count"):
            cards = storefront_page.get_product_cards()
            assert len(cards) == 6, f"Expected 6 products, found {len(cards)}"

        with allure.step("Verify product card attributes"):
            first_card = cards[0]
            assert "Keyboard" in first_card.get_title_text()
            assert first_card.get_price_value() == 149.99

    @allure.story("Real-time Search Filtering")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_filters_products_in_realtime(self, storefront_page: StorefrontPage):
        """Types query in search bar and asserts only matching items remain."""
        with allure.step("Type search query 'Headphones'"):
            storefront_page.header.search_for("Headphones")
            cards = storefront_page.get_product_cards()
            assert len(cards) == 1
            assert "Headphones" in cards[0].get_title_text()

        with allure.step("Clear search input"):
            storefront_page.header.clear_search()
            assert len(storefront_page.get_product_cards()) == 6

    @allure.story("Category Filter Navigation")
    @allure.severity(allure.severity_level.NORMAL)
    def test_category_filter_chips(self, storefront_page: StorefrontPage):
        """Clicks category chips and asserts only category items are displayed."""
        with allure.step("Filter by 'Accessories' category"):
            storefront_page.header.select_category("Accessories")
            cards = storefront_page.get_product_cards()
            assert len(cards) == 1
            assert "Cable" in cards[0].get_title_text()

        with allure.step("Filter by 'All' category"):
            storefront_page.header.select_category("all")
            assert len(storefront_page.get_product_cards()) == 6

    @allure.story("Product Price Sorting")
    @allure.severity(allure.severity_level.MINOR)
    def test_sort_products_by_price(self, storefront_page: StorefrontPage):
        """Sorts catalog price low-to-high and asserts ordering."""
        with allure.step("Select Sort Low-to-High"):
            storefront_page.sort_by("price-asc")
            prices = storefront_page.get_all_product_prices()
            assert prices == sorted(prices), f"Prices not sorted ascending: {prices}"

    @allure.story("Empty Search State & Recovery")
    @allure.severity(allure.severity_level.NORMAL)
    def test_empty_search_state_and_reset_button(self, storefront_page: StorefrontPage):
        """Searches for non-existent item and clicks reset button."""
        with allure.step("Search for non-existent term"):
            storefront_page.header.search_for("NonExistentXYZ")
            expect(storefront_page.empty_state_card).to_be_visible()

        with allure.step("Click reset filter button"):
            storefront_page.reset_filters_btn.click()
            expect(storefront_page.empty_state_card).to_be_hidden()
            assert len(storefront_page.get_product_cards()) == 6
