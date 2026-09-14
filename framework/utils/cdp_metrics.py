"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from typing import Any

from playwright.sync_api import Page


class CDPTelemetryCollector:
    """Extracts raw performance metrics and Core Web Vitals via CDP and Navigation Timing APIs."""

    def __init__(self, page: Page):
        self.page = page

    def capture_cdp_metrics(self) -> dict[str, float]:
        """Captures raw CDP Performance metrics via Chrome DevTools session."""
        try:
            cdp_session = self.page.context.new_cdp_session(self.page)
            cdp_session.send("Performance.enable")
            metrics_data = cdp_session.send("Performance.getMetrics")
            cdp_session.detach()

            result = {}
            for metric in metrics_data.get("metrics", []):
                result[metric["name"]] = metric["value"]
            return result
        except (RuntimeError, KeyError, TypeError, ValueError) as e:
            return {"error": str(e)}

    def get_performance_metrics(self) -> dict[str, float]:
        """Alias for capture_cdp_metrics."""
        return self.capture_cdp_metrics()

    def capture_web_vitals(self) -> dict[str, Any]:
        """Calculates Core Web Vitals (LCP, CLS, FCP, TTFB, DOM Interactive) from page performance entries."""
        vitals_script = """
        () => {
            const nav = performance.getEntriesByType('navigation')[0] || {};
            const paint = performance.getEntriesByType('paint') || [];
            
            const fcpEntry = paint.find(entry => entry.name === 'first-contentful-paint');
            const fcp = fcpEntry ? fcpEntry.startTime : 0;
            
            const ttfb = nav.responseStart ? (nav.responseStart - nav.requestStart) : 0;
            const domInteractive = nav.domInteractive ? (nav.domInteractive - nav.startTime) : 0;
            const domComplete = nav.domComplete ? (nav.domComplete - nav.startTime) : 0;
            
            // Collect layout shifts
            let cls = 0;
            const shifts = performance.getEntriesByType('layout-shift') || [];
            for (const shift of shifts) {
                if (!shift.hadRecentInput) {
                    cls += shift.value;
                }
            }

            return {
                fcp_ms: Math.round(fcp),
                ttfb_ms: Math.round(ttfb),
                dom_interactive_ms: Math.round(domInteractive),
                dom_complete_ms: Math.round(domComplete),
                cls_score: parseFloat(cls.toFixed(4)),
                dom_nodes_count: document.querySelectorAll('*').length
            };
        }
        """
        try:
            return self.page.evaluate(vitals_script)
        except (RuntimeError, TypeError, ValueError) as e:
            return {"error": str(e)}
