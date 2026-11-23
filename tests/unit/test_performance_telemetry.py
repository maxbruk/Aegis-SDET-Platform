"""Unit tests for CDPTelemetryCollector and PerformanceThresholdEvaluator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error as PlaywrightError

from framework.telemetry.performance import (
    CDPTelemetryCollector,
    PerformanceThresholdEvaluator,
    PerformanceThresholds,
    TelemetryCollectionError,
)


@pytest.mark.unit
class TestPerformanceTelemetry:
    """Verifies CDP session cleanup, typed errors, and threshold separation."""

    def test_cdp_session_always_detaches_on_error(self) -> None:
        mock_session = MagicMock()
        mock_session.send.side_effect = [None, RuntimeError("CDP protocol crash")]
        mock_page = MagicMock()
        mock_page.context.new_cdp_session.return_value = mock_session

        collector = CDPTelemetryCollector(mock_page)
        with pytest.raises(TelemetryCollectionError):
            collector.capture_cdp_metrics()

        mock_session.detach.assert_called_once()

    def test_cdp_session_detaches_on_playwright_error(self) -> None:
        mock_session = MagicMock()
        mock_session.send.side_effect = [None, PlaywrightError("Target closed")]
        mock_page = MagicMock()
        mock_page.context.new_cdp_session.return_value = mock_session

        collector = CDPTelemetryCollector(mock_page)
        with pytest.raises(TelemetryCollectionError):
            collector.capture_cdp_metrics()

        mock_session.detach.assert_called_once()

    def test_capture_cdp_metrics_returns_pure_float_dict(self) -> None:
        mock_session = MagicMock()
        mock_session.send.side_effect = [
            None,
            {"metrics": [{"name": "JSHeapUsedSize", "value": 1048576}]},
        ]
        mock_page = MagicMock()
        mock_page.context.new_cdp_session.return_value = mock_session

        collector = CDPTelemetryCollector(mock_page)
        metrics = collector.capture_cdp_metrics()

        assert metrics == {"JSHeapUsedSize": 1048576.0}
        mock_session.detach.assert_called_once()

    def test_threshold_evaluator_flags_sla_violations(self) -> None:
        metrics = {
            "ttfb_ms": 120,
            "fcp_ms": 900,
            "lcp_ms": 3200,
            "cls_score": 0.18,
            "inp_ms": 80,
            "js_heap_used_mb": 14.5,
            "api_latency_ms": 35.0,
        }
        thresholds = PerformanceThresholds(
            max_fcp_ms=2500.0,
            max_lcp_ms=2500.0,
            max_cls_score=0.1,
            max_inp_ms=200.0,
        )
        evaluation = PerformanceThresholdEvaluator.evaluate(metrics, thresholds)

        assert evaluation.passed is False
        violated_metrics = {v.metric for v in evaluation.violations}
        assert violated_metrics == {"lcp_ms", "cls_score"}
