"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from playwright.sync_api import Locator, Page


class CartItemComponent:
    """Encapsulates a single line item row in the Cart Drawer."""

    def __init__(self, root: Locator):
        self.root = root
        self.increment_btn: Locator = root.locator('[data-testid="qty-increment-btn"]')
        self.decrement_btn: Locator = root.locator('[data-testid="qty-decrement-btn"]')
        self.remove_btn: Locator = root.locator('[data-testid="cart-item-remove-btn"]')
        self.qty_value: Locator = root.locator('[data-testid="cart-item-qty"]')

    def get_quantity(self) -> int:
        return int(self.qty_value.inner_text().strip())

    def increment_quantity(self) -> None:
        self.increment_btn.click()

    def decrement_quantity(self) -> None:
        self.decrement_btn.click()

    def remove(self) -> None:
        self.remove_btn.click()


class CartDrawerComponent:
    """Encapsulates the slide-over shopping cart drawer."""

    def __init__(self, page: Page):
        self.page = page
        self.drawer: Locator = page.locator('[data-testid="cart-drawer"]')
        self.drawer_container: Locator = self.drawer
        self.overlay: Locator = page.locator('[data-testid="cart-drawer-overlay"]')
        self.close_btn: Locator = page.locator('[data-testid="cart-close-btn"]')
        self.item_count_badge: Locator = page.locator('[data-testid="drawer-item-count"]')

        # Empty View
        self.empty_view: Locator = page.locator('[data-testid="cart-empty-view"]')
        self.empty_message: Locator = page.locator('[data-testid="empty-cart-msg"]')
        self.start_shopping_btn: Locator = page.locator('[data-testid="cart-start-shopping-btn"]')

        # Items View
        self.items_container: Locator = page.locator('[data-testid="cart-items-container"]')
        self.items_list: Locator = page.locator('[data-testid="cart-items-list"]')
        self.cart_items: Locator = page.locator('[data-testid="cart-item"]')

        # Footer & Totals
        self.footer: Locator = page.locator('[data-testid="cart-footer"]')
        self.subtotal: Locator = page.locator('[data-testid="cart-subtotal"]')
        self.tax: Locator = page.locator('[data-testid="cart-tax"]')
        self.total: Locator = page.locator('[data-testid="cart-total"]')
        self.checkout_btn: Locator = page.locator('[data-testid="checkout-btn"]')
        self.clear_cart_btn: Locator = page.locator('[data-testid="clear-cart-btn"]')

    def is_open(self) -> bool:
        """Returns whether the cart drawer is open."""
        return "open" in (self.drawer.get_attribute("class") or "")

    def close(self) -> None:
        """Closes the drawer."""
        self.close_btn.click()

    def get_items_count(self) -> int:
        """Returns number of items listed in cart."""
        return self.cart_items.count()

    def get_cart_items(self) -> list[CartItemComponent]:
        """Returns list of CartItemComponent instances."""
        locators = self.cart_items.all()
        return [CartItemComponent(loc) for loc in locators]

    def get_totals(self) -> tuple[float, float, float]:
        """Returns subtotal, tax, and total as floats."""
        subtotal = float(self.subtotal.inner_text().replace("$", "").strip())
        tax = float(self.tax.inner_text().replace("$", "").strip())
        total = float(self.total.inner_text().replace("$", "").strip())
        return subtotal, tax, total

    def get_subtotal_value(self) -> float:
        return float(self.subtotal.inner_text().replace("$", "").strip())

    def get_total_value(self) -> float:
        return float(self.total.inner_text().replace("$", "").strip())

    def increment_quantity(self, product_id: int) -> None:
        btn = self.page.locator(
            f'[data-testid="cart-item"][data-product-id="{product_id}"] [data-testid="qty-increment-btn"]'
        )
        btn.click()

    def decrement_quantity(self, product_id: int) -> None:
        btn = self.page.locator(
            f'[data-testid="cart-item"][data-product-id="{product_id}"] [data-testid="qty-decrement-btn"]'
        )
        btn.click()

    def remove_item(self, product_id: int) -> None:
        btn = self.page.locator(
            f'[data-testid="cart-item"][data-product-id="{product_id}"] [data-testid="cart-item-remove-btn"]'
        )
        btn.click()

    def clear_all_items(self) -> None:
        self.clear_cart_btn.click()

    def clear_cart(self) -> None:
        self.clear_all_items()

    def proceed_to_checkout(self) -> None:
        self.checkout_btn.click()
