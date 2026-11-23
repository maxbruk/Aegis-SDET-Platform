"""Orchestrated failure intelligence report generator (never masks failed test status)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from framework.ai.classifier import FailureCategory, FailureClassification, FailureClassifier
from framework.ai.history import HistoricalFailureStore, HistoricalMatch
from framework.ai.locator_healer import (
    HealingAuditRecord,
    LocatorHealer,
    LocatorValidationEngine,
)
from framework.artifacts.manager import sanitize_artifact_name
from framework.execution.run_context import RunContext

if TYPE_CHECKING:
    from playwright.sync_api import Page


class FailureIntelligenceReport(BaseModel):
    """Diagnostic analysis attached to failed tests without modifying test pass/fail status."""

    test_id: str
    run_id: str
    test_status: Literal["failed"] = "failed"
    classification: FailureClassification
    suggested_resolution: str
    locator_audit: HealingAuditRecord | None = None
    similar_historical_failures: list[HistoricalMatch] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


_CATEGORY_RESOLUTIONS: dict[FailureCategory, str] = {
    FailureCategory.INFRASTRUCTURE_FAILURE: (
        "Verify Docker services, PostgreSQL, and Go backend /health status before rerunning."
    ),
    FailureCategory.NETWORK_FAILURE: (
        "Inspect failed_requests JSON and Go backend logs for HTTP 5xx or transport resets."
    ),
    FailureCategory.LOCATOR_FAILURE: (
        "Review suggested locator candidate; validate intent and approve manually before editing."
    ),
    FailureCategory.APPLICATION_ERROR: (
        "Inspect browser console logs and Playwright trace for uncaught frontend exceptions."
    ),
    FailureCategory.TIMEOUT_FAILURE: (
        "Inspect Playwright trace timeline and network latency for stalled state transitions."
    ),
    FailureCategory.ASSERTION_FAILURE: (
        "Compare expected domain state against captured screenshot and API payloads."
    ),
    FailureCategory.UNKNOWN: (
        "Inspect failure screenshot, Playwright trace ZIP, and console logs for root cause."
    ),
}


class FailureIntelligenceAnalyzer:
    """Combines failure classification, locator healing validation, and historical lookup."""

    def __init__(
        self,
        run_context: RunContext | None = None,
        history_store: HistoricalFailureStore | None = None,
    ) -> None:
        self.run_context = run_context or RunContext()
        self.history_store = history_store or HistoricalFailureStore()

    def analyze_failure(
        self,
        test_id: str,
        error_message: str,
        stack_trace: str = "",
        console_logs: str = "",
        failed_network_requests: Sequence[dict[str, object]] = (),
        dom_html: str | None = None,
        page: Page | None = None,
        artifact_paths: dict[str, str] | None = None,
    ) -> FailureIntelligenceReport:
        """Analyze failure evidence, validate any locator candidate, and save diagnostic JSON."""
        classification = FailureClassifier.classify(
            error_message=error_message,
            stack_trace=stack_trace,
            console_logs=console_logs,
            failed_network_requests=failed_network_requests,
        )

        locator_audit: HealingAuditRecord | None = None
        if classification.category == FailureCategory.LOCATOR_FAILURE and (
            dom_html is not None or page is not None
        ):
            failed_loc = LocatorHealer.extract_failed_locator(f"{error_message}\n{stack_trace}")
            if failed_loc:
                snapshot_html = dom_html if dom_html is not None else page.content()  # type: ignore[union-attr]
                candidates = LocatorHealer.suggest_candidates(failed_loc, snapshot_html)
                if candidates:
                    selected_cand = candidates[0]
                    selected_val = (
                        LocatorValidationEngine.validate_against_page(selected_cand, page)
                        if page is not None
                        else LocatorValidationEngine.validate_against_html(
                            selected_cand, snapshot_html
                        )
                    )
                    if selected_val.validation_status != "validated":
                        for cand in candidates[1:]:
                            probe_val = (
                                LocatorValidationEngine.validate_against_page(cand, page)
                                if page is not None
                                else LocatorValidationEngine.validate_against_html(
                                    cand, snapshot_html
                                )
                            )
                            if probe_val.validation_status == "validated":
                                selected_cand = cand
                                selected_val = probe_val
                                break
                    locator_audit = HealingAuditRecord(
                        test_id=test_id,
                        failed_locator=failed_loc,
                        suggested_locator=selected_cand.playwright_expression,
                        confidence=selected_cand.confidence,
                        validation_status=selected_val.validation_status,
                        probe_passed=selected_val.probe_passed,
                        approval_status=(
                            "pending_human_approval"
                            if selected_val.validation_status == "validated"
                            else "rejected"
                        ),
                        explanation=f"{selected_cand.rationale} ({selected_val.reason})",
                    )

        similar = self.history_store.find_similar(error_message)
        self.history_store.record_failure(
            run_id=self.run_context.run_id,
            test_id=test_id,
            category=classification.category.value,
            error_message=error_message,
        )

        report = FailureIntelligenceReport(
            test_id=test_id,
            run_id=self.run_context.run_id,
            test_status="failed",
            classification=classification,
            suggested_resolution=_CATEGORY_RESOLUTIONS[classification.category],
            locator_audit=locator_audit,
            similar_historical_failures=similar,
            artifact_paths=dict(artifact_paths or {}),
        )
        self.save_report(report)
        return report

    def save_report(self, report: FailureIntelligenceReport) -> Path:
        """Persist the AI diagnostic JSON to reports/runs/<run_id>/ai_diagnostics/."""
        self.run_context.ensure_directories()
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
        target = (
            self.run_context.ai_diagnostics_dir
            / f"ai_{worker_id}_{sanitize_artifact_name(report.test_id)}.json"
        )
        target.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return target
