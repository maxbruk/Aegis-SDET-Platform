"""Unit tests for the VisualDiffer regression engine."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from framework.quality.visual import VIEWPORT_PROFILES, VisualDiffer, VisualMetadata


def _make_image(path: Path, size: tuple[int, int] = (100, 100), color=(255, 255, 255)) -> Path:
    Image.new("RGB", size, color=color).save(path)
    return path


@pytest.mark.unit
class TestVisualDiffer:
    """Covers identical, small diff, large diff, missing baseline, dimension mismatch, and boundary cases."""

    def test_identical_images_pass_with_zero_mismatch(self, tmp_path: Path) -> None:
        baseline = _make_image(tmp_path / "baseline.png")
        actual = _make_image(tmp_path / "actual.png")
        diff_out = tmp_path / "diff.png"

        result = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=baseline,
            diff_output_path=diff_out,
            mismatch_threshold_percent=1.0,
            metadata=VisualMetadata(browser="chromium", viewport="1280x800", dpr=1.0),
        )
        assert result.passed is True
        assert result.mismatch_percent == 0.0
        assert result.reason == "matched"
        assert not diff_out.exists()

    def test_small_pixel_difference_within_threshold_passes(self, tmp_path: Path) -> None:
        baseline = _make_image(tmp_path / "baseline.png", size=(100, 100))
        actual_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        # Modify 50 pixels (0.5% of 10,000 pixels)
        draw = ImageDraw.Draw(actual_img)
        draw.rectangle([0, 0, 9, 4], fill=(0, 0, 0))
        actual = tmp_path / "actual.png"
        actual_img.save(actual)
        diff_out = tmp_path / "diff.png"

        result = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=baseline,
            diff_output_path=diff_out,
            mismatch_threshold_percent=1.0,
        )
        assert result.passed is True
        assert pytest.approx(result.mismatch_percent, abs=0.05) == 0.5
        assert result.reason == "within_threshold"

    def test_large_pixel_difference_fails_and_writes_diff_and_side_by_side(
        self, tmp_path: Path
    ) -> None:
        baseline = _make_image(tmp_path / "baseline.png", size=(100, 100))
        actual_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        # Modify 2500 pixels (25% of 10,000 pixels)
        draw = ImageDraw.Draw(actual_img)
        draw.rectangle([0, 0, 49, 49], fill=(0, 0, 0))
        actual = tmp_path / "actual.png"
        actual_img.save(actual)
        diff_out = tmp_path / "artifacts" / "diff.png"

        result = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=baseline,
            diff_output_path=diff_out,
            mismatch_threshold_percent=1.0,
        )
        assert result.passed is False
        assert result.reason == "pixel_mismatch"
        assert pytest.approx(result.mismatch_percent, abs=0.1) == 25.0
        assert result.diff_output_path is not None and Path(result.diff_output_path).exists()
        assert result.side_by_side_path is not None and Path(result.side_by_side_path).exists()
        with Image.open(result.side_by_side_path) as composite:
            assert composite.width == 100 * 3 + 16
            assert composite.height == 100

    def test_missing_baseline_fails_by_default_and_creates_only_on_explicit_update(
        self, tmp_path: Path
    ) -> None:
        actual = _make_image(tmp_path / "actual.png")
        missing_baseline = tmp_path / "baselines" / "missing.png"
        diff_out = tmp_path / "diff.png"

        res_default = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=missing_baseline,
            diff_output_path=diff_out,
            update_baselines=False,
        )
        assert res_default.passed is False
        assert res_default.reason == "baseline_missing"
        assert not missing_baseline.exists()

        res_update = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=missing_baseline,
            diff_output_path=diff_out,
            update_baselines=True,
        )
        assert res_update.passed is True
        assert res_update.reason == "baseline_created"
        assert missing_baseline.exists()

    def test_dimension_mismatch_fails_without_resizing(self, tmp_path: Path) -> None:
        baseline = _make_image(tmp_path / "baseline.png", size=(100, 100))
        actual = _make_image(tmp_path / "actual.png", size=(120, 100))
        diff_out = tmp_path / "diff.png"

        result = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=baseline,
            diff_output_path=diff_out,
            mismatch_threshold_percent=50.0,
        )
        assert result.passed is False
        assert result.reason == "dimension_mismatch"
        assert result.actual_size == (120, 100)
        assert result.baseline_size == (100, 100)

    def test_threshold_boundary_equality_passes_and_exceeding_fails(self, tmp_path: Path) -> None:
        baseline = _make_image(tmp_path / "baseline.png", size=(100, 100))
        actual_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        # Modify exactly 100 pixels = 1.00%
        draw = ImageDraw.Draw(actual_img)
        draw.rectangle([0, 0, 9, 9], fill=(0, 0, 0))
        actual = tmp_path / "actual.png"
        actual_img.save(actual)
        diff_out = tmp_path / "diff.png"

        pass_at_exact = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=baseline,
            diff_output_path=diff_out,
            mismatch_threshold_percent=1.0,
        )
        assert pass_at_exact.passed is True
        assert pass_at_exact.mismatch_percent == 1.0

        fail_below = VisualDiffer.compare_images_detailed(
            actual_path=actual,
            baseline_path=baseline,
            diff_output_path=diff_out,
            mismatch_threshold_percent=0.99,
        )
        assert fail_below.passed is False
        assert fail_below.reason == "pixel_mismatch"

    def test_viewport_profiles_define_desktop_tablet_mobile(self) -> None:
        assert set(VIEWPORT_PROFILES.keys()) == {"desktop", "tablet", "mobile"}
        assert VIEWPORT_PROFILES["tablet"].width == 768
