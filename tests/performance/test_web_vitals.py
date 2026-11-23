"""Performance telemetry tests measuring Web Vitals and CDP metrics."""

import allure
import pytest

from framework.pages.storefront_page import StorefrontPage
from framework.telemetry.browser import collect_browser_runtime_snapshot
from framework.telemetry.performance import (
    CDPTelemetryCollector,
    PerformanceThresholdEvaluator,
    PerformanceThresholds,
)


@allure.epic("Performance & Telemetry")
@allure.feature("Core Web Vitals & CDP Metrics")
@pytest.mark.performance
class TestCoreWebVitals:
    """Performance telemetry tests measuring TTFB, FCP, LCP, CLS, INP, Heap, and API latency."""

    @allure.story("Core Web Vitals Threshold SLA")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_storefront_core_web_vitals_thresholds(
        self,
        storefront_page: StorefrontPage,
        cdp_collector: CDPTelemetryCollector,
    ) -> None:
        """Exercise real UI interactions, collect Web Vitals, and evaluate SLA thresholds."""
        with allure.step("Trigger real category interactions for INP observation"):
            storefront_page.header.select_category("Electronics")
            storefront_page.header.select_category("all")
            snapshot = collect_browser_runtime_snapshot(storefront_page.page)
            assert snapshot["readyState"] in {"interactive", "complete"}
            assert snapshot["domNodes"] > 10

        with allure.step("Capture Web Vitals and runtime metrics"):
            vitals = cdp_collector.capture_web_vitals()
            for required_key in (
                "ttfb_ms",
                "fcp_ms",
                "lcp_ms",
                "cls_score",
                "inp_ms",
                "dom_nodes_count",
                "js_heap_used_mb",
                "api_latency_ms",
            ):
                assert required_key in vitals, f"Missing telemetry metric: {required_key}"
            assert vitals["dom_nodes_count"] > 10, "Unexpectedly low DOM node count"

        with allure.step("Evaluate metrics against SLA thresholds"):
            thresholds = PerformanceThresholds(
                max_fcp_ms=2500.0,
                max_lcp_ms=2500.0,
                max_cls_score=0.1,
                max_inp_ms=200.0,
            )
            evaluation = PerformanceThresholdEvaluator.evaluate(vitals, thresholds)
            assert evaluation.passed, f"Web Vitals SLA violations: {evaluation.violations}"

    @allure.story("CDP Performance Metrics Extraction")
    @allure.severity(allure.severity_level.NORMAL)
    def test_cdp_metrics_extraction(
        self,
        storefront_page: StorefrontPage,
        cdp_collector: CDPTelemetryCollector,
    ) -> None:
        """Extract low-level layout and JS heap metrics from Chromium CDP."""
        del storefront_page
        with allure.step("Query CDP Performance.getMetrics"):
            metrics = cdp_collector.get_performance_metrics()
            assert isinstance(metrics, dict)
            assert len(metrics) > 0
            assert all(isinstance(v, float) for v in metrics.values())
            assert "JSHeapUsedSize" in metrics
