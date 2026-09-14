"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from playwright.sync_api import Locator, Page


class AuthModalComponent:
    """Encapsulates Sign In and Register tabbed modal interactions."""

    def __init__(self, page: Page):
        self.page = page
        self.modal: Locator = page.locator('[data-testid="auth-modal"]')
        self.close_btn: Locator = page.locator('[data-testid="auth-close-btn"]')
        self.error_banner: Locator = page.locator('[data-testid="auth-error"]')

        # Tabs
        self.tab_login: Locator = page.locator('[data-testid="tab-login"]')
        self.tab_register: Locator = page.locator('[data-testid="tab-register"]')

        # Login Form
        self.login_form: Locator = page.locator('[data-testid="login-form"]')
        self.login_email: Locator = page.locator('[data-testid="login-email"]')
        self.login_password: Locator = page.locator('[data-testid="login-password"]')
        self.login_submit_btn: Locator = page.locator('[data-testid="login-submit-btn"]')

        # Register Form
        self.register_form: Locator = page.locator('[data-testid="register-form"]')
        self.register_name: Locator = page.locator('[data-testid="register-name"]')
        self.register_email: Locator = page.locator('[data-testid="register-email"]')
        self.register_password: Locator = page.locator('[data-testid="register-password"]')
        self.register_submit_btn: Locator = page.locator('[data-testid="register-submit-btn"]')

    def switch_to_login(self) -> None:
        self.tab_login.click()

    def switch_to_register(self) -> None:
        self.tab_register.click()

    def login(self, email: str, password: str) -> None:
        self.switch_to_login()
        self.login_email.fill(email)
        self.login_password.fill(password)
        self.login_submit_btn.click()

    def register(self, name: str, email: str, password: str) -> None:
        self.switch_to_register()
        self.register_name.fill(name)
        self.register_email.fill(email)
        self.register_password.fill(password)
        self.register_submit_btn.click()

    def close(self) -> None:
        self.close_btn.click()
