"""Performance telemetry collector (CDP + Web Vitals) and SLA threshold evaluator."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from framework.config.settings import settings

logger = logging.getLogger(__name__)


class TelemetryCollectionError(RuntimeError):
    """Raised when CDP or PerformanceObserver telemetry cannot be collected."""


@dataclass(frozen=True, slots=True)
class PerformanceThresholds:
    """Configurable SLA thresholds for Web Vitals and runtime resource metrics."""

    max_ttfb_ms: float | None = None
    max_fcp_ms: float | None = 2500.0
    max_lcp_ms: float | None = 2500.0
    max_cls_score: float | None = 0.1
    max_inp_ms: float | None = 200.0
    max_js_heap_mb: float | None = None
    max_api_latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class ThresholdViolation:
    """Single SLA violation reported by PerformanceThresholdEvaluator."""

    metric: str
    actual: float
    threshold: float


@dataclass(slots=True)
class ThresholdEvaluationResult:
    """Outcome of comparing collected performance metrics against PerformanceThresholds."""

    passed: bool
    violations: list[ThresholdViolation] = field(default_factory=list)
    metrics: dict[str, float | int] = field(default_factory=dict)


class PerformanceThresholdEvaluator:
    """Separates metric collection from SLA threshold verification."""

    _METRIC_TO_THRESHOLD = (
        ("ttfb_ms", "max_ttfb_ms"),
        ("fcp_ms", "max_fcp_ms"),
        ("lcp_ms", "max_lcp_ms"),
        ("cls_score", "max_cls_score"),
        ("inp_ms", "max_inp_ms"),
        ("js_heap_used_mb", "max_js_heap_mb"),
        ("api_latency_ms", "max_api_latency_ms"),
    )

    @classmethod
    def evaluate(
        cls,
        metrics: dict[str, float | int],
        thresholds: PerformanceThresholds,
    ) -> ThresholdEvaluationResult:
        """Evaluate captured telemetry metrics against configured thresholds."""
        violations: list[ThresholdViolation] = []
        for metric_key, threshold_attr in cls._METRIC_TO_THRESHOLD:
            limit = getattr(thresholds, threshold_attr)
            if limit is None or metric_key not in metrics:
                continue
            actual_val = float(metrics[metric_key])
            if actual_val > limit:
                violations.append(
                    ThresholdViolation(
                        metric=metric_key,
                        actual=actual_val,
                        threshold=limit,
                    )
                )
        return ThresholdEvaluationResult(
            passed=len(violations) == 0,
            violations=violations,
            metrics=dict(metrics),
        )


_WEB_VITALS_SCRIPT = """
async () => {
    const observeBuffered = (entryType) => new Promise((resolve) => {
        const entries = [];
        try {
            if (!PerformanceObserver.supportedEntryTypes || !PerformanceObserver.supportedEntryTypes.includes(entryType)) {
                resolve(entries);
                return;
            }
            const observer = new PerformanceObserver((list) => {
                for (const item of list.getEntries()) {
                    entries.push(item);
                }
            });
            observer.observe({ type: entryType, buffered: true });
            setTimeout(() => {
                try {
                    const pending = observer.takeRecords();
                    for (const item of pending) entries.push(item);
                    observer.disconnect();
                } catch (_) {}
                resolve(entries);
            }, 60);
        } catch (_) {
            resolve(entries);
        }
    });

    const [lcpEntries, clsEntries, eventEntries, firstInputEntries] = await Promise.all([
        observeBuffered('largest-contentful-paint'),
        observeBuffered('layout-shift'),
        observeBuffered('event'),
        observeBuffered('first-input'),
    ]);

    const nav = performance.getEntriesByType('navigation')[0] || {};
    const paint = performance.getEntriesByType('paint') || [];
    const fcpEntry = paint.find((entry) => entry.name === 'first-contentful-paint');
    const fcpMs = fcpEntry ? fcpEntry.startTime : 0;

    const ttfbMs = nav.responseStart ? Math.max(0, nav.responseStart - nav.requestStart) : 0;
    const domInteractiveMs = nav.domInteractive ? Math.max(0, nav.domInteractive - nav.startTime) : 0;
    const domCompleteMs = nav.domComplete ? Math.max(0, nav.domComplete - nav.startTime) : 0;

    // Largest Contentful Paint (fallback to FCP if no buffered LCP candidate fired)
    const lastLcp = lcpEntries.length > 0 ? lcpEntries[lcpEntries.length - 1] : null;
    const lcpMs = lastLcp ? lastLcp.startTime : fcpMs;

    // Session-windowed CLS (max 5s window, <=1s gap between shifts, excluding hadRecentInput)
    let maxSessionCls = 0;
    let sessionValue = 0;
    let sessionStart = 0;
    let prevShiftTime = 0;
    for (const shift of clsEntries) {
        if (shift.hadRecentInput) continue;
        if (
            prevShiftTime === 0 ||
            (shift.startTime - prevShiftTime <= 1000 && shift.startTime - sessionStart <= 5000)
        ) {
            if (prevShiftTime === 0) sessionStart = shift.startTime;
            sessionValue += shift.value;
        } else {
            sessionStart = shift.startTime;
            sessionValue = shift.value;
        }
        prevShiftTime = shift.startTime;
        if (sessionValue > maxSessionCls) maxSessionCls = sessionValue;
    }

    // Interaction to Next Paint (INP) filtered by non-zero interactionId events
    let inpMs = 0;
    const interactionEvents = eventEntries.filter(
        (entry) => typeof entry.interactionId === 'number' && entry.interactionId > 0
    );
    if (interactionEvents.length > 0) {
        const byInteraction = new Map();
        for (const entry of interactionEvents) {
            const prev = byInteraction.get(entry.interactionId) || 0;
            if (typeof entry.duration === 'number' && entry.duration > prev) {
                byInteraction.set(entry.interactionId, entry.duration);
            }
        }
        const durations = Array.from(byInteraction.values()).sort((a, b) => a - b);
        const idx = Math.min(durations.length - 1, Math.floor(durations.length * 0.98));
        inpMs = durations[idx] || 0;
    } else {
        for (const entry of firstInputEntries) {
            if (typeof entry.duration === 'number' && entry.duration > inpMs) {
                inpMs = entry.duration;
            }
        }
    }

    // API latency average across /api/ and /health resource entries
    const resources = performance.getEntriesByType('resource') || [];
    const apiResources = resources.filter(
        (r) => typeof r.name === 'string' && (r.name.includes('/api/') || r.name.endsWith('/health'))
    );
    const apiLatencyMs = apiResources.length > 0
        ? apiResources.reduce((acc, r) => acc + r.duration, 0) / apiResources.length
        : 0;

    return {
        ttfb_ms: Math.round(ttfbMs),
        fcp_ms: Math.round(fcpMs),
        lcp_ms: Math.round(lcpMs),
        cls_score: parseFloat(maxSessionCls.toFixed(4)),
        inp_ms: Math.round(inpMs),
        dom_interactive_ms: Math.round(domInteractiveMs),
        dom_complete_ms: Math.round(domCompleteMs),
        dom_nodes_count: document.querySelectorAll('*').length,
        api_latency_ms: parseFloat(apiLatencyMs.toFixed(2)),
    };
}
"""


class CDPTelemetryCollector:
    """Extracts CDP performance metrics and Core Web Vitals via PerformanceObserver."""

    def __init__(self, page: Page) -> None:
        self.page = page

    def capture_cdp_metrics(self) -> dict[str, float]:
        """Capture numeric CDP Performance.getMetrics values, detaching session safely."""
        cdp_session = None
        try:
            cdp_session = self.page.context.new_cdp_session(self.page)
            cdp_session.send("Performance.enable")
            metrics_data = cdp_session.send("Performance.getMetrics")
            result: dict[str, float] = {}
            for metric in metrics_data.get("metrics", []):
                result[str(metric["name"])] = float(metric["value"])
            return result
        except (PlaywrightError, RuntimeError, KeyError, TypeError, ValueError) as exc:
            raise TelemetryCollectionError(f"Failed to capture CDP metrics: {exc}") from exc
        finally:
            if cdp_session is not None:
                with contextlib.suppress(PlaywrightError, RuntimeError):
                    cdp_session.detach()

    def get_performance_metrics(self) -> dict[str, float]:
        """Alias for capture_cdp_metrics."""
        return self.capture_cdp_metrics()

    def capture_web_vitals(self, push_telemetry: bool | None = None) -> dict[str, float | int]:
        """Capture Web Vitals, DOM metrics, API latency, and JS heap usage."""
        try:
            vitals: dict[str, Any] = self.page.evaluate(_WEB_VITALS_SCRIPT)
        except (PlaywrightError, RuntimeError, TypeError, ValueError) as exc:
            raise TelemetryCollectionError(f"Failed to evaluate Web Vitals script: {exc}") from exc

        js_heap_mb = 0.0
        try:
            cdp_metrics = self.capture_cdp_metrics()
            js_heap_bytes = cdp_metrics.get("JSHeapUsedSize", 0.0)
            js_heap_mb = round(js_heap_bytes / (1024.0 * 1024.0), 3)
        except TelemetryCollectionError:
            pass

        vitals["js_heap_used_mb"] = js_heap_mb
        should_push = settings.REQUIRE_BACKEND if push_telemetry is None else push_telemetry
        if should_push:
            self._push_web_vitals(vitals)
        return vitals

    @staticmethod
    def _push_web_vitals(vitals: dict[str, float | int]) -> None:
        """Forward captured Web Vitals gauges to backend/Prometheus when reachable."""
        payload = {
            "web_vitals": {
                "ttfb_ms": float(vitals.get("ttfb_ms", 0.0)),
                "fcp_ms": float(vitals.get("fcp_ms", 0.0)),
                "lcp_ms": float(vitals.get("lcp_ms", 0.0)),
                "cls_score": float(vitals.get("cls_score", 0.0)),
                "inp_ms": float(vitals.get("inp_ms", 0.0)),
                "js_heap_mb": float(vitals.get("js_heap_used_mb", 0.0)),
            }
        }
        try:
            httpx.post(
                f"{settings.API_URL.rstrip('/')}/api/v1/telemetry/ingest",
                json=payload,
                timeout=0.3,
            )
        except httpx.HTTPError as exc:
            logger.debug("Skipping Web Vitals telemetry push (offline): %s", exc)
