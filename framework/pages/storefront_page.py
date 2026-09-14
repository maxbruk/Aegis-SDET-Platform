"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from playwright.sync_api import Locator, Page

from framework.pages.base_page import BasePage
from framework.pages.components.auth_modal import AuthModalComponent
from framework.pages.components.cart_drawer import CartDrawerComponent
from framework.pages.components.checkout_modal import CheckoutModalComponent
from framework.pages.components.header import HeaderComponent
from framework.pages.components.product_card import ProductCardComponent
from framework.pages.components.toast import ToastComponent


class StorefrontPage(BasePage):
    """Main Storefront Page Object combining Component Object Model abstractions."""

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

        # Sub-components
        self.header = HeaderComponent(page)
        self.cart_drawer = CartDrawerComponent(page)
        self.checkout_modal = CheckoutModalComponent(page)
        self.auth_modal = AuthModalComponent(page)
        self.toast = ToastComponent(page)

        # Page-specific locators
        self.page_title: Locator = page.locator('[data-testid="page-title"]')
        self.catalog_count_text: Locator = page.locator('[data-testid="catalog-count-text"]')
        self.sort_select: Locator = page.locator('[data-testid="sort-select"]')
        self.product_grid: Locator = page.locator('[data-testid="product-grid"]')
        self.empty_state: Locator = page.locator('[data-testid="catalog-empty"]')
        self.empty_state_card: Locator = self.empty_state
        self.reset_filter_btn: Locator = page.locator('[data-testid="reset-filter-btn"]')
        self.reset_filters_btn: Locator = self.reset_filter_btn
        self.offline_banner: Locator = page.locator('[data-testid="offline-banner"]')

    def open(self) -> "StorefrontPage":
        """Navigates to the storefront home page."""
        self.navigate("/")
        self.wait_for_dom_ready()
        self.page.locator('[data-testid="product-card"]').first.wait_for(
            state="visible", timeout=5000
        )
        return self

    def get_product_cards(self) -> list[ProductCardComponent]:
        """Returns a list of ProductCardComponent instances for all visible cards."""
        locators = self.product_grid.locator('[data-testid="product-card"]').all()
        return [ProductCardComponent(loc) for loc in locators]

    def get_all_product_prices(self) -> list[float]:
        """Returns all visible product prices as floats."""
        return [card.get_price_value() for card in self.get_product_cards()]

    def get_product_card_by_id(self, product_id: int) -> ProductCardComponent:
        """Returns the ProductCardComponent for a specific product ID."""
        locator = self.product_grid.locator(
            f'[data-testid="product-card"][data-product-id="{product_id}"]'
        )
        return ProductCardComponent(locator)

    def sort_by(self, sort_value: str) -> None:
        """Select a sort option ('price-asc', 'price-desc', 'name-asc', 'featured')."""
        self.sort_select.select_option(sort_value)

    def reset_filters(self) -> None:
        """Click the reset filters button."""
        self.reset_filter_btn.click()
