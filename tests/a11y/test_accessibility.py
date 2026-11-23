"""Automated accessibility testing suite for Storefront views, modals, and keyboard focus."""

import allure
import pytest
from playwright.sync_api import Browser

from framework.pages.storefront_page import StorefrontPage
from framework.quality.accessibility import AccessibilityAuditor


@allure.epic("Accessibility (A11y)")
@allure.feature("Automated Accessibility Testing")
@pytest.mark.a11y
class TestAccessibilityAudits:
    """Automated accessibility checks for DOM controls, modals, and keyboard navigation."""

    @allure.story("Storefront Home Automated Accessibility Check")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_storefront_home_accessibility_compliance(
        self,
        storefront_page: StorefrontPage,
        axe_auditor: AccessibilityAuditor,
    ) -> None:
        """Audit main storefront view with zero tolerance for axe-core or DOM violations."""
        del storefront_page
        with allure.step("Run automated accessibility checks on Storefront"):
            violations = axe_auditor.audit_page()
            assert violations == [], f"A11y violations found: {violations}"

        with allure.step("Verify keyboard Tab navigation moves across interactive controls"):
            nav_result = axe_auditor.check_keyboard_navigation(steps=5)
            assert nav_result["passed"] is True
            assert nav_result["visited_count"] >= 2

    @allure.story("Auth Modal Automated Accessibility Check")
    @allure.severity(allure.severity_level.NORMAL)
    def test_auth_modal_accessibility_compliance(
        self,
        storefront_page: StorefrontPage,
        axe_auditor: AccessibilityAuditor,
    ) -> None:
        """Audit authentication dialog ARIA role, aria-modal, labels, and focusable controls."""
        with allure.step("Open auth modal"):
            storefront_page.header.open_auth_modal()
            storefront_page.page.wait_for_function(
                "() => document.getAnimations().every((a) => a.playState !== 'running')"
            )

        with allure.step("Audit modal ARIA attributes and form labels"):
            violations = axe_auditor.audit_page()
            assert violations == [], f"A11y violations in Auth modal: {violations}"

            modal_issues = axe_auditor.check_modal_accessibility("#auth-modal")
            assert modal_issues == [], f"Auth modal ARIA issues: {modal_issues}"

    @allure.story("Cart Drawer Automated Accessibility Check")
    @allure.severity(allure.severity_level.NORMAL)
    def test_cart_drawer_accessibility_compliance(
        self,
        storefront_page: StorefrontPage,
        axe_auditor: AccessibilityAuditor,
    ) -> None:
        """Audit slide-over Cart Drawer for accessible buttons and dialog semantics."""
        with allure.step("Add product and open cart drawer"):
            card = storefront_page.get_product_card_by_id(1)
            card.add_to_cart()
            storefront_page.header.open_cart()
            storefront_page.page.wait_for_function(
                "() => document.getAnimations().every((a) => a.playState !== 'running')"
            )

        with allure.step("Audit cart drawer accessibility"):
            violations = axe_auditor.audit_page()
            assert violations == [], f"A11y violations in Cart Drawer: {violations}"

            drawer_issues = axe_auditor.check_modal_accessibility("#cart-drawer")
            assert drawer_issues == [], f"Cart drawer ARIA issues: {drawer_issues}"

    @allure.story("Controlled Violation Detection in Browser")
    @allure.severity(allure.severity_level.NORMAL)
    def test_auditor_flags_unlabeled_controls_and_invalid_modal_in_browser(
        self, browser: Browser
    ) -> None:
        """Prove AccessibilityAuditor + axe-core detect unlabeled controls and broken modals."""
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.set_content(
                """
                <!DOCTYPE html>
                <html lang="en">
                  <body>
                    <input id="email" type="email" placeholder="Enter email">
                    <button id="icon-btn"></button>
                    <div id="bad-modal" class="modal-backdrop">
                      <button id="close-btn">Close</button>
                    </div>
                  </body>
                </html>
                """
            )
            auditor = AccessibilityAuditor(page)
            report = auditor.run_audit()
            rules = {v["rule"] for v in report["violations"]}
            assert report["passes"] is False
            assert "label" in rules
            assert "button-name" in rules

            modal_issues = auditor.check_modal_accessibility("#bad-modal")
            modal_rules = {issue["rule"] for issue in modal_issues}
            assert {"dialog-role", "dialog-aria-modal", "dialog-accessible-name"} <= modal_rules
        finally:
            page.close()
            ctx.close()
