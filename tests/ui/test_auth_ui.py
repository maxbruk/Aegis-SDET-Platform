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
from framework.utils.data_factory import DataFactory


@allure.epic("Authentication & User Session")
@allure.feature("Auth Modal & JWT State Management")
@pytest.mark.ui
@pytest.mark.ui_mocked
class TestAuthUI:
    """End-to-end tests for Login, Registration, and Session management in Storefront UI."""

    @allure.story("Open & Close Auth Modal")
    @allure.severity(allure.severity_level.NORMAL)
    def test_open_and_close_auth_modal(self, mocked_storefront_page: StorefrontPage):
        """Verifies opening the auth modal via header button and closing it via close button."""
        with allure.step("Click Sign In button in header"):
            mocked_storefront_page.header.open_auth_modal()
            expect(mocked_storefront_page.auth_modal.modal).to_be_visible()

        with allure.step("Click Close button in auth modal"):
            mocked_storefront_page.auth_modal.close()
            expect(mocked_storefront_page.auth_modal.modal).to_be_hidden()

    @allure.story("Switch Between Login and Register Tabs")
    @allure.severity(allure.severity_level.NORMAL)
    def test_switch_between_login_and_register_tabs(self, mocked_storefront_page: StorefrontPage):
        """Verifies tab switching toggles between Login and Register form inputs."""
        with allure.step("Open modal and switch to Register tab"):
            mocked_storefront_page.header.open_auth_modal()
            mocked_storefront_page.auth_modal.switch_to_register()
            expect(mocked_storefront_page.auth_modal.register_form).to_be_visible()
            expect(mocked_storefront_page.auth_modal.login_form).to_be_hidden()

        with allure.step("Switch back to Login tab"):
            mocked_storefront_page.auth_modal.switch_to_login()
            expect(mocked_storefront_page.auth_modal.login_form).to_be_visible()
            expect(mocked_storefront_page.auth_modal.register_form).to_be_hidden()

    @allure.story("Register New Customer Account")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_register_new_account_flow(
        self,
        mocked_storefront_page: StorefrontPage,
        data_factory: DataFactory,
    ):
        """Completes new customer registration and verifies session state."""
        user = data_factory.random_user()

        with allure.step(f"Register new account: {user['email']}"):
            mocked_storefront_page.header.open_auth_modal()
            mocked_storefront_page.auth_modal.switch_to_register()
            mocked_storefront_page.auth_modal.register(
                name=user["name"],
                email=user["email"],
                password=user["password"],
            )

        with allure.step("Assert user badge is visible in header"):
            expect(mocked_storefront_page.header.user_menu).to_be_visible()
            expect(mocked_storefront_page.header.auth_open_btn).to_be_hidden()

    @allure.story("User Logout Flow")
    @allure.severity(allure.severity_level.NORMAL)
    def test_user_logout_flow(
        self,
        mocked_storefront_page: StorefrontPage,
        data_factory: DataFactory,
    ):
        """Registers a user and subsequently logs out, asserting session is destroyed."""
        user = data_factory.random_user()

        with allure.step("Authenticate session"):
            mocked_storefront_page.header.open_auth_modal()
            mocked_storefront_page.auth_modal.switch_to_register()
            mocked_storefront_page.auth_modal.register(
                name=user["name"],
                email=user["email"],
                password=user["password"],
            )
            expect(mocked_storefront_page.header.user_menu).to_be_visible()

        with allure.step("Execute logout"):
            mocked_storefront_page.header.logout()
            expect(mocked_storefront_page.header.user_menu).to_be_hidden()
            expect(mocked_storefront_page.header.auth_open_btn).to_be_visible()
