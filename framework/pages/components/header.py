"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from playwright.sync_api import Locator, Page


class HeaderComponent:
    """Encapsulates the navigation header, search bar, auth controls, and cart badge."""

    def __init__(self, page: Page):
        self.page = page
        self.brand_logo: Locator = page.locator('[data-testid="brand-logo"]')
        self.search_input: Locator = page.locator('[data-testid="search-input"]')
        self.search_clear_btn: Locator = page.locator('[data-testid="search-clear-btn"]')
        self.api_status_badge: Locator = page.locator('[data-testid="api-status-badge"]')

        # Auth elements
        self.auth_open_btn: Locator = page.locator('[data-testid="auth-btn"]')
        self.user_menu: Locator = page.locator('[data-testid="user-menu"]')
        self.user_profile_btn: Locator = page.locator('[data-testid="user-profile-btn"]')
        self.user_display_name: Locator = page.locator('[data-testid="user-display-name"]')
        self.user_role_badge: Locator = page.locator('[data-testid="user-role-badge"]')
        self.user_dropdown: Locator = page.locator('[data-testid="user-dropdown"]')
        self.admin_panel_link: Locator = page.locator('[data-testid="admin-panel-link"]')
        self.logout_btn: Locator = page.locator('[data-testid="logout-btn"]')

        # Cart Button
        self.cart_btn: Locator = page.locator('[data-testid="cart-btn"]')
        self.cart_count_badge: Locator = page.locator('[data-testid="cart-count"]')

        # Category Filter Nav
        self.category_nav: Locator = page.locator('[data-testid="category-nav"]')

    def search(self, query: str) -> None:
        """Search products by query."""
        self.search_input.fill(query)

    def search_for(self, query: str) -> None:
        """Search products by query (alias)."""
        self.search(query)

    def clear_search(self) -> None:
        """Clear search input."""
        self.search_clear_btn.click()

    def select_category(self, category_name: str) -> None:
        """Filter products by clicking a category chip."""
        chip = self.page.locator(f'[data-testid="category-filter-{category_name.lower()}"]')
        chip.click()

    def open_auth_modal(self) -> None:
        """Click the Sign In button in header."""
        self.auth_open_btn.click()

    def open_cart_drawer(self) -> None:
        """Open the slide-over shopping cart drawer."""
        self.cart_btn.click()

    def open_cart(self) -> None:
        """Alias for open_cart_drawer."""
        self.open_cart_drawer()

    def get_cart_count(self) -> int:
        """Return the integer count displayed on the cart badge."""
        return int(self.cart_count_badge.inner_text())

    def open_admin_panel(self) -> None:
        """Open the admin panel dropdown link."""
        self.user_profile_btn.click()
        self.admin_panel_link.click()

    def logout(self) -> None:
        """Log out the current user via profile dropdown."""
        self.user_profile_btn.click()
        self.logout_btn.click()
