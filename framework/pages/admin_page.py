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
from framework.pages.components.toast import ToastComponent


class AdminPage(BasePage):
    """Encapsulates Admin Inventory RBAC modal and management functions."""

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        self.modal: Locator = page.locator('[data-testid="admin-modal"]')
        self.admin_modal: Locator = self.modal
        self.close_btn: Locator = page.locator('[data-testid="admin-close-btn"]')
        self.toast = ToastComponent(page)

        # Create Product Form
        self.create_form: Locator = page.locator('[data-testid="admin-create-product-form"]')
        self.product_name_input: Locator = page.locator('[data-testid="admin-product-name"]')
        self.product_price_input: Locator = page.locator('[data-testid="admin-product-price"]')
        self.product_stock_input: Locator = page.locator('[data-testid="admin-product-stock"]')
        self.product_category_select: Locator = page.locator(
            '[data-testid="admin-product-category"]'
        )
        self.product_desc_input: Locator = page.locator('[data-testid="admin-product-desc"]')
        self.submit_product_btn: Locator = page.locator('[data-testid="admin-submit-product-btn"]')

        # Inventory Table
        self.inventory_table: Locator = page.locator('[data-testid="admin-inventory-table"]')
        self.inventory_tbody: Locator = page.locator('[data-testid="admin-inventory-tbody"]')
        self.product_rows: Locator = page.locator('[data-testid="admin-product-row"]')

    def open_inventory_modal(self) -> None:
        """Opens the admin inventory modal from header user menu."""
        self.page.locator('[data-testid="user-profile-btn"]').click()
        self.page.locator('[data-testid="admin-panel-link"]').click()

    def is_modal_visible(self) -> bool:
        return self.modal.is_visible()

    def create_product(
        self, name: str, price: float, stock: int, category: str, description: str
    ) -> None:
        """Fills out the new product form and submits it."""
        self.product_name_input.fill(name)
        self.product_price_input.fill(str(price))
        self.product_stock_input.fill(str(stock))
        self.product_category_select.select_option(category)
        self.product_desc_input.fill(description)
        self.submit_product_btn.click()

    def delete_product(self, product_id: int) -> None:
        """Deletes a product row by its ID."""
        btn = self.page.locator(
            f'[data-testid="admin-product-row"][data-product-id="{product_id}"] [data-testid="admin-delete-product-btn"]'
        )
        btn.click()

    def get_row_count(self) -> int:
        return self.product_rows.count()

    def close(self) -> None:
        self.close_btn.click()
