"""Visual regression suite comparing live rendering against golden baselines."""

from pathlib import Path

import allure
import pytest

from framework.config.settings import settings
from framework.execution.run_context import RunContext
from framework.pages.storefront_page import StorefrontPage
from framework.quality.visual import VIEWPORT_PROFILES, VisualDiffer, VisualMetadata


@allure.epic("Visual Regression")
@allure.feature("Pixel-Level Layout Verification")
@pytest.mark.visual
class TestVisualRegression:
    """Visual regression suite using strict dimension checks and highlighted diff artifacts."""

    @allure.story("Desktop 1280x800 Layout Baseline")
    @allure.severity(allure.severity_level.NORMAL)
    def test_storefront_desktop_layout(
        self,
        storefront_page: StorefrontPage,
        visual_checker: VisualDiffer,
        run_context: RunContext,
    ) -> None:
        """Verify desktop 1280x800 layout matches golden baseline snapshot."""
        profile = VIEWPORT_PROFILES["desktop"]
        run_context.ensure_directories()
        baseline = "reports/artifacts/visual_baselines/storefront_desktop.png"
        actual = run_context.screenshots_dir / "storefront_desktop_actual.png"
        diff = run_context.screenshots_dir / "storefront_desktop_diff.png"

        with allure.step("Capture 1280x800 desktop full-page screenshot"):
            storefront_page.page.set_viewport_size(
                {"width": profile.width, "height": profile.height}
            )
            storefront_page.page.screenshot(
                path=str(actual),
                full_page=True,
                animations="disabled",
                caret="hide",
            )

        with allure.step("Compare screenshot with baseline"):
            result = visual_checker.compare_images_detailed(
                actual_path=actual,
                baseline_path=baseline,
                diff_output_path=diff,
                mismatch_threshold_percent=7.5,
                metadata=VisualMetadata(
                    browser=settings.BROWSER_NAME,
                    viewport=f"{profile.width}x{profile.height}",
                    dpr=profile.device_scale_factor,
                ),
            )
            if not result.passed:
                for label, path_str in (
                    ("Desktop Diff Mask", result.diff_output_path),
                    ("Desktop Side-by-Side", result.side_by_side_path),
                ):
                    if path_str and Path(path_str).exists():
                        allure.attach.file(
                            path_str, name=label, attachment_type=allure.attachment_type.PNG
                        )
            assert result.passed, (
                f"Desktop visual regression failed ({result.reason}, "
                f"{result.mismatch_percent:.2f}% mismatch)."
            )

    @allure.story("Mobile 375x812 Viewport Baseline")
    @allure.severity(allure.severity_level.NORMAL)
    def test_storefront_mobile_viewport(
        self,
        storefront_page: StorefrontPage,
        visual_checker: VisualDiffer,
        run_context: RunContext,
    ) -> None:
        """Verify mobile 375x812 layout matches golden baseline snapshot."""
        profile = VIEWPORT_PROFILES["mobile"]
        run_context.ensure_directories()
        baseline = "reports/artifacts/visual_baselines/storefront_mobile.png"
        actual = run_context.screenshots_dir / "storefront_mobile_actual.png"
        diff = run_context.screenshots_dir / "storefront_mobile_diff.png"

        with allure.step("Capture 375x812 mobile full-page screenshot"):
            storefront_page.page.set_viewport_size(
                {"width": profile.width, "height": profile.height}
            )
            storefront_page.page.screenshot(
                path=str(actual),
                full_page=True,
                animations="disabled",
                caret="hide",
            )

        with allure.step("Compare screenshot with baseline"):
            result = visual_checker.compare_images_detailed(
                actual_path=actual,
                baseline_path=baseline,
                diff_output_path=diff,
                mismatch_threshold_percent=7.5,
                metadata=VisualMetadata(
                    browser=settings.BROWSER_NAME,
                    viewport=f"{profile.width}x{profile.height}",
                    dpr=profile.device_scale_factor,
                ),
            )
            if not result.passed:
                for label, path_str in (
                    ("Mobile Diff Mask", result.diff_output_path),
                    ("Mobile Side-by-Side", result.side_by_side_path),
                ):
                    if path_str and Path(path_str).exists():
                        allure.attach.file(
                            path_str, name=label, attachment_type=allure.attachment_type.PNG
                        )
            assert result.passed, (
                f"Mobile visual regression failed ({result.reason}, "
                f"{result.mismatch_percent:.2f}% mismatch)."
            )
