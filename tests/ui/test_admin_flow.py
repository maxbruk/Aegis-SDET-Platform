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

from framework.pages.admin_page import AdminPage
from framework.utils.data_factory import DataFactory


@allure.epic("Admin & Inventory")
@allure.feature("Role-Based Inventory Management")
@pytest.mark.ui
class TestAdminInventoryFlow:
    """Tests admin CRUD interactions and RBAC access."""

    @allure.story("Admin Product Creation & Inventory Management")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_admin_creates_and_deletes_product(
        self,
        admin_page: Page,
        live_server: str,
        data_factory: DataFactory,
    ):
        """Verifies an admin can open inventory manager, create a product, and view it in table."""
        admin = AdminPage(admin_page, live_server)
        product_data = data_factory.random_product()

        with allure.step("Open Admin inventory modal"):
            admin.open_inventory_modal()
            expect(admin.admin_modal).to_be_visible()

        with allure.step(f"Create product '{product_data['name']}'"):
            admin.create_product(
                name=product_data["name"],
                price=product_data["price"],
                stock=product_data["stock"],
                category=product_data["category"],
                description=product_data["description"],
            )

        with allure.step("Assert newly created product appears in inventory table"):
            expect(admin.inventory_table).to_contain_text(product_data["name"])
