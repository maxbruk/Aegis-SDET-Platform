"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import os

import allure
import pytest

from framework.pages.storefront_page import StorefrontPage
from framework.utils.visual_differ import VisualDiffer


@allure.epic("Visual Regression")
@allure.feature("Pixel-Level Layout Verification")
@pytest.mark.visual
class TestVisualRegression:
    """Visual regression suite comparing live rendering against golden baselines with perceptual diffing."""

    @allure.story("Desktop 1280x800 Layout Baseline")
    @allure.severity(allure.severity_level.NORMAL)
    def test_storefront_desktop_layout(
        self,
        storefront_page: StorefrontPage,
        visual_checker: VisualDiffer,
    ):
        """Verifies desktop 1280x800 layout matches baseline snapshot."""
        os.makedirs("reports/artifacts/visual_baselines", exist_ok=True)
        baseline = "reports/artifacts/visual_baselines/storefront_desktop.png"
        actual = "reports/artifacts/storefront_desktop_actual.png"
        diff = "reports/artifacts/storefront_desktop_diff.png"

        with allure.step("Capture 1280x800 desktop full-page screenshot"):
            storefront_page.page.set_viewport_size({"width": 1280, "height": 800})
            storefront_page.page.screenshot(path=actual, full_page=True)

        with allure.step("Compare screenshot with baseline"):
            passed, mismatch_pct = visual_checker.compare_images(
                actual_path=actual,
                baseline_path=baseline,
                diff_output_path=diff,
                mismatch_threshold_percent=7.5,
            )
            assert passed, (
                f"Desktop visual regression failed with {mismatch_pct:.2f}% pixel mismatch."
            )

    @allure.story("Mobile 375x812 Viewport Baseline")
    @allure.severity(allure.severity_level.NORMAL)
    def test_storefront_mobile_viewport(
        self,
        storefront_page: StorefrontPage,
        visual_checker: VisualDiffer,
    ):
        """Verifies mobile 375x812 (iPhone 13 size) layout matches baseline snapshot."""
        os.makedirs("reports/artifacts/visual_baselines", exist_ok=True)
        baseline = "reports/artifacts/visual_baselines/storefront_mobile.png"
        actual = "reports/artifacts/storefront_mobile_actual.png"
        diff = "reports/artifacts/storefront_mobile_diff.png"

        with allure.step("Capture 375x812 mobile full-page screenshot"):
            storefront_page.page.set_viewport_size({"width": 375, "height": 812})
            storefront_page.page.screenshot(path=actual, full_page=True)

        with allure.step("Compare screenshot with baseline"):
            passed, mismatch_pct = visual_checker.compare_images(
                actual_path=actual,
                baseline_path=baseline,
                diff_output_path=diff,
                mismatch_threshold_percent=7.5,
            )
            assert passed, (
                f"Mobile visual regression failed with {mismatch_pct:.2f}% pixel mismatch."
            )
