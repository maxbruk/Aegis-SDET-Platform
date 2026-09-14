"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import os

from PIL import Image, ImageChops


class VisualDiffer:
    """Performs pixel-level layout and screenshot comparisons with tolerance thresholds."""

    @staticmethod
    def compare_images(
        actual_path: str,
        baseline_path: str,
        diff_output_path: str,
        mismatch_threshold_percent: float = 1.0,
    ) -> tuple[bool, float]:
        """Compares two images and writes a visual diff mask if deviations exceed threshold."""
        if not os.path.exists(baseline_path):
            # If baseline doesn't exist yet, save actual as baseline
            os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
            img = Image.open(actual_path)
            img.save(baseline_path)
            return True, 0.0

        img_actual = Image.open(actual_path).convert("RGB")
        img_baseline = Image.open(baseline_path).convert("RGB")

        # Resize if dimensions differ slightly due to viewport
        if img_actual.size != img_baseline.size:
            img_actual = img_actual.resize(img_baseline.size)

        diff = ImageChops.difference(img_actual, img_baseline)
        bbox = diff.getbbox()

        if not bbox:
            return True, 0.0

        # Calculate percentage of differing pixels (ignoring subpixel anti-aliasing noise < 12 luminance)
        stat = diff.convert("L")
        histogram = stat.histogram()
        total_pixels = img_actual.width * img_actual.height
        perceptual_diff_pixels = sum(histogram[12:])
        mismatch_percent = (perceptual_diff_pixels / total_pixels) * 100.0

        if mismatch_percent > mismatch_threshold_percent:
            os.makedirs(os.path.dirname(diff_output_path), exist_ok=True)
            diff.save(diff_output_path)
            return False, mismatch_percent

        return True, mismatch_percent
