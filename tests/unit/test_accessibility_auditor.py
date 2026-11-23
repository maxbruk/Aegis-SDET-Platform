"""Pure unit tests for AccessibilityAuditor normalization, multi-node aggregation, and keyboard checks."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from framework.quality.accessibility import AccessibilityAuditor


@pytest.mark.unit
class TestAccessibilityAuditor:
    """Verifies AccessibilityAuditor logic without launching a browser binary."""

    def test_run_audit_merges_multi_node_axe_violations_and_deduplicates(self) -> None:
        mock_page = MagicMock()
        mock_page.evaluate.side_effect = [
            {
                "engine": "aegis-builtin",
                "passes": False,
                "violation_count": 1,
                "violations": [
                    {
                        "rule": "label",
                        "impact": "critical",
                        "severity": "critical",
                        "selector": "#email",
                        "description": "Missing label",
                        "suggestion": "Add label",
                    }
                ],
            },
            True,  # window.axe !== 'undefined' (when path check triggers)
            True,  # second typeof window.axe check
            {
                "violations": [
                    {
                        "id": "color-contrast",
                        "impact": "serious",
                        "description": "Insufficient contrast",
                        "help": "Increase contrast",
                        "nodes": [
                            {"target": ["#badge-1"]},
                            {"target": ["#badge-2"]},
                        ],
                    }
                ]
            },
        ]

        auditor = AccessibilityAuditor(mock_page)
        report = auditor.run_audit()

        assert report["engine"] == "axe-core+aegis"
        assert report["passes"] is False
        assert report["violation_count"] == 2
        contrast = next(v for v in report["violations"] if v["rule"] == "color-contrast")
        assert "#badge-1" in contrast["selector"]
        assert "#badge-2" in contrast["selector"]

    def test_check_keyboard_navigation_fails_on_single_element_focus_trap(self) -> None:
        mock_page = MagicMock()
        mock_page.evaluate.return_value = "#trapped-btn"
        auditor = AccessibilityAuditor(mock_page)

        trapped = auditor.check_keyboard_navigation(steps=4, min_distinct=2)
        assert trapped["passed"] is False
        assert trapped["visited_count"] == 1

    def test_check_keyboard_navigation_passes_when_multiple_controls_visited(self) -> None:
        mock_page = MagicMock()
        mock_page.evaluate.side_effect = ["#search-input", "#auth-open-btn", "#cart-toggle-btn"]
        auditor = AccessibilityAuditor(mock_page)

        ok = auditor.check_keyboard_navigation(steps=3, min_distinct=2)
        assert ok["passed"] is True
        assert ok["visited_count"] == 3
        assert ok["visited_selectors"] == ["#search-input", "#auth-open-btn", "#cart-toggle-btn"]
