"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from playwright.sync_api import Locator


class ProductCardComponent:
    """Encapsulates interactions with an individual product card in the catalog grid."""

    def __init__(self, root: Locator):
        self.root = root
        self.category: Locator = root.locator('[data-testid="product-category"]')
        self.title: Locator = root.locator('[data-testid="product-title"]')
        self.description: Locator = root.locator('[data-testid="product-description"]')
        self.price: Locator = root.locator('[data-testid="product-price"]')
        self.stock: Locator = root.locator('[data-testid="product-stock"]')
        self.add_to_cart_btn: Locator = root.locator('[data-testid="add-to-cart-btn"]')

    def get_title_text(self) -> str:
        return self.title.inner_text()

    def get_price_value(self) -> float:
        text = self.price.inner_text().replace("$", "").strip()
        return float(text)

    def add_to_cart(self) -> None:
        self.add_to_cart_btn.click()
