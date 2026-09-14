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

from framework.pages.storefront_page import StorefrontPage
from framework.utils.a11y_auditor import AccessibilityAuditor


@allure.epic("Accessibility (A11y)")
@allure.feature("WCAG 2.1 AA Compliance Audits")
@pytest.mark.a11y
class TestAccessibilityAudits:
    """Automated WCAG 2.1 AA compliance audits for DOM elements, form controls, and dialogs."""

    @allure.story("Storefront Home Accessibility Compliance")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_storefront_home_accessibility_compliance(
        self,
        storefront_page: StorefrontPage,
        axe_auditor: AccessibilityAuditor,
    ):
        """Audits main storefront view for form labels, ARIA landmarks, and unique IDs."""
        with allure.step("Run full page WCAG audit on Storefront"):
            violations = axe_auditor.audit_page()
            critical_violations = [v for v in violations if v["severity"] == "critical"]
            assert len(critical_violations) == 0, (
                f"Critical A11y violations found: {critical_violations}"
            )

    @allure.story("Auth Modal Accessibility Compliance")
    @allure.severity(allure.severity_level.NORMAL)
    def test_auth_modal_accessibility_compliance(
        self,
        storefront_page: StorefrontPage,
        axe_auditor: AccessibilityAuditor,
    ):
        """Audits authentication dialog for focus traps and input labelling."""
        with allure.step("Open auth modal"):
            storefront_page.header.open_auth_modal()

        with allure.step("Audit modal ARIA attributes and form labels"):
            violations = axe_auditor.audit_page()
            critical_violations = [v for v in violations if v["severity"] == "critical"]
            assert len(critical_violations) == 0, (
                f"A11y violations in Auth modal: {critical_violations}"
            )

    @allure.story("Cart Drawer Accessibility Compliance")
    @allure.severity(allure.severity_level.NORMAL)
    def test_cart_drawer_accessibility_compliance(
        self,
        storefront_page: StorefrontPage,
        axe_auditor: AccessibilityAuditor,
    ):
        """Audits slide-over Cart Drawer for accessible buttons and ARIA semantics."""
        with allure.step("Add product and open cart drawer"):
            card = storefront_page.get_product_card_by_id(1)
            card.add_to_cart()
            storefront_page.header.open_cart()

        with allure.step("Audit cart drawer WCAG compliance"):
            violations = axe_auditor.audit_page()
            critical_violations = [v for v in violations if v["severity"] == "critical"]
            assert len(critical_violations) == 0, (
                f"A11y violations in Cart Drawer: {critical_violations}"
            )
