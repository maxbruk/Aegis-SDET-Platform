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
from framework.utils.cdp_metrics import CDPTelemetryCollector


@allure.epic("Performance & Telemetry")
@allure.feature("Core Web Vitals & CDP Metrics")
@pytest.mark.performance
class TestCoreWebVitals:
    """Performance telemetry tests measuring LCP, CLS, FCP, TTFB, and DOM metrics via CDP."""

    @allure.story("Core Web Vitals Threshold SLA")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_storefront_core_web_vitals_thresholds(
        self,
        storefront_page: StorefrontPage,
        cdp_collector: CDPTelemetryCollector,
    ):
        """Measures First Contentful Paint and Cumulative Layout Shift on Storefront home."""
        with allure.step("Capture performance entries"):
            vitals = cdp_collector.capture_web_vitals()

        with allure.step("Assert Web Vitals SLAs"):
            assert vitals["fcp_ms"] < 2500, f"FCP threshold exceeded: {vitals['fcp_ms']}ms"
            assert vitals["cls_score"] <= 0.1, f"CLS score exceeded: {vitals['cls_score']}"
            assert vitals["dom_nodes_count"] > 10, "Unexpectedly low DOM node count"

    @allure.story("CDP Performance Metrics Extraction")
    @allure.severity(allure.severity_level.NORMAL)
    def test_cdp_metrics_extraction(
        self,
        storefront_page: StorefrontPage,
        cdp_collector: CDPTelemetryCollector,
    ):
        """Extracts low-level layout and JS heap performance metrics directly from Chromium CDP."""
        with allure.step("Query CDP Performance.getMetrics"):
            metrics = cdp_collector.get_performance_metrics()
            assert isinstance(metrics, dict)
            assert len(metrics) > 0
