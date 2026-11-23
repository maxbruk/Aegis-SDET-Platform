"""Visual regression comparison engine with strict baseline and dimension checks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance

from framework.config.settings import settings


@dataclass(frozen=True, slots=True)
class ViewportProfile:
    """Standardized viewport profile for visual regression snapshots."""

    name: str
    width: int
    height: int
    device_scale_factor: float = 1.0


VIEWPORT_PROFILES: dict[str, ViewportProfile] = {
    "desktop": ViewportProfile(name="desktop", width=1280, height=800, device_scale_factor=1.0),
    "tablet": ViewportProfile(name="tablet", width=768, height=1024, device_scale_factor=1.0),
    "mobile": ViewportProfile(name="mobile", width=375, height=812, device_scale_factor=1.0),
}


@dataclass(frozen=True, slots=True)
class VisualMetadata:
    """Context metadata attached to a visual comparison snapshot."""

    browser: str = "chromium"
    viewport: str = "1280x800"
    dpr: float = 1.0
    locale: str = "en-US"


@dataclass(slots=True)
class VisualComparisonResult:
    """Detailed outcome of a pixel-level visual regression comparison."""

    passed: bool
    mismatch_percent: float
    reason: str
    baseline_path: str
    actual_path: str
    diff_output_path: str | None = None
    side_by_side_path: str | None = None
    actual_size: tuple[int, int] | None = None
    baseline_size: tuple[int, int] | None = None
    metadata: VisualMetadata | None = None


class VisualDiffer:
    """Performs strict pixel-level screenshot comparisons without silent masking."""

    @staticmethod
    def update_baseline(actual_path: str | Path, baseline_path: str | Path) -> Path:
        """Explicitly copy an actual screenshot into the golden baseline location."""
        target = Path(baseline_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(actual_path) as img:
            img.convert("RGB").save(target)
        return target

    @staticmethod
    def _build_highlight_mask(
        img_actual: Image.Image,
        img_baseline: Image.Image,
        diff: Image.Image,
    ) -> Image.Image:
        """Render differing pixels in bright red over a dimmed baseline image."""
        dimmed = ImageEnhance.Brightness(img_baseline).enhance(0.4)
        luminance = diff.convert("L")
        mask = luminance.point(lambda px: 255 if px >= 12 else 0)
        red_overlay = Image.new("RGB", img_actual.size, (239, 68, 68))
        dimmed.paste(red_overlay, mask=mask)
        return dimmed

    @staticmethod
    def _build_side_by_side(
        img_baseline: Image.Image,
        diff_highlight: Image.Image,
        img_actual: Image.Image,
    ) -> Image.Image:
        """Compose baseline, highlighted diff, and actual images horizontally."""
        width, height = img_baseline.size
        gap = 8
        canvas = Image.new("RGB", (width * 3 + gap * 2, height), (30, 41, 59))
        canvas.paste(img_baseline, (0, 0))
        canvas.paste(diff_highlight, (width + gap, 0))
        canvas.paste(img_actual, (width * 2 + gap * 2, 0))
        return canvas

    @classmethod
    def compare_images_detailed(
        cls,
        actual_path: str | Path,
        baseline_path: str | Path,
        diff_output_path: str | Path,
        mismatch_threshold_percent: float = 1.0,
        update_baselines: bool | None = None,
        metadata: VisualMetadata | None = None,
    ) -> VisualComparisonResult:
        """Compare actual screenshot to golden baseline and generate diff artifacts on failure."""
        actual_str = str(actual_path)
        baseline_str = str(baseline_path)
        diff_str = str(diff_output_path)
        should_update = (
            settings.UPDATE_VISUAL_BASELINES if update_baselines is None else update_baselines
        )

        if not os.path.exists(baseline_str):
            if should_update:
                cls.update_baseline(actual_str, baseline_str)
                with Image.open(actual_str) as img:
                    size = img.size
                return VisualComparisonResult(
                    passed=True,
                    mismatch_percent=0.0,
                    reason="baseline_created",
                    baseline_path=baseline_str,
                    actual_path=actual_str,
                    actual_size=size,
                    baseline_size=size,
                    metadata=metadata,
                )
            return VisualComparisonResult(
                passed=False,
                mismatch_percent=100.0,
                reason="baseline_missing",
                baseline_path=baseline_str,
                actual_path=actual_str,
                metadata=metadata,
            )

        with Image.open(actual_str) as raw_actual, Image.open(baseline_str) as raw_baseline:
            img_actual = raw_actual.convert("RGB")
            img_baseline = raw_baseline.convert("RGB")

        if img_actual.size != img_baseline.size:
            if should_update:
                cls.update_baseline(actual_str, baseline_str)
                return VisualComparisonResult(
                    passed=True,
                    mismatch_percent=0.0,
                    reason="baseline_updated",
                    baseline_path=baseline_str,
                    actual_path=actual_str,
                    actual_size=img_actual.size,
                    baseline_size=img_actual.size,
                    metadata=metadata,
                )
            return VisualComparisonResult(
                passed=False,
                mismatch_percent=100.0,
                reason="dimension_mismatch",
                baseline_path=baseline_str,
                actual_path=actual_str,
                actual_size=img_actual.size,
                baseline_size=img_baseline.size,
                metadata=metadata,
            )

        diff = ImageChops.difference(img_actual, img_baseline)
        bbox = diff.getbbox()
        if not bbox:
            return VisualComparisonResult(
                passed=True,
                mismatch_percent=0.0,
                reason="matched",
                baseline_path=baseline_str,
                actual_path=actual_str,
                actual_size=img_actual.size,
                baseline_size=img_baseline.size,
                metadata=metadata,
            )

        stat = diff.convert("L")
        histogram = stat.histogram()
        total_pixels = img_actual.width * img_actual.height
        perceptual_diff_pixels = sum(histogram[12:])
        mismatch_percent = (perceptual_diff_pixels / total_pixels) * 100.0

        if mismatch_percent > mismatch_threshold_percent:
            if should_update:
                cls.update_baseline(actual_str, baseline_str)
                return VisualComparisonResult(
                    passed=True,
                    mismatch_percent=0.0,
                    reason="baseline_updated",
                    baseline_path=baseline_str,
                    actual_path=actual_str,
                    actual_size=img_actual.size,
                    baseline_size=img_actual.size,
                    metadata=metadata,
                )

            diff_target = Path(diff_str)
            diff_target.parent.mkdir(parents=True, exist_ok=True)
            highlighted = cls._build_highlight_mask(img_actual, img_baseline, diff)
            highlighted.save(diff_target)

            side_by_side_target = diff_target.with_name(f"{diff_target.stem}_side_by_side.png")
            composite = cls._build_side_by_side(img_baseline, highlighted, img_actual)
            composite.save(side_by_side_target)

            return VisualComparisonResult(
                passed=False,
                mismatch_percent=mismatch_percent,
                reason="pixel_mismatch",
                baseline_path=baseline_str,
                actual_path=actual_str,
                diff_output_path=str(diff_target),
                side_by_side_path=str(side_by_side_target),
                actual_size=img_actual.size,
                baseline_size=img_baseline.size,
                metadata=metadata,
            )

        return VisualComparisonResult(
            passed=True,
            mismatch_percent=mismatch_percent,
            reason="within_threshold",
            baseline_path=baseline_str,
            actual_path=actual_str,
            actual_size=img_actual.size,
            baseline_size=img_baseline.size,
            metadata=metadata,
        )

    @classmethod
    def compare_images(
        cls,
        actual_path: str,
        baseline_path: str,
        diff_output_path: str,
        mismatch_threshold_percent: float = 1.0,
        update_baselines: bool | None = None,
    ) -> tuple[bool, float]:
        """Compare actual image to baseline and return (passed, mismatch_percent)."""
        result = cls.compare_images_detailed(
            actual_path=actual_path,
            baseline_path=baseline_path,
            diff_output_path=diff_output_path,
            mismatch_threshold_percent=mismatch_threshold_percent,
            update_baselines=update_baselines,
        )
        return result.passed, result.mismatch_percent
