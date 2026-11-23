"""Deterministic multi-signal failure classifier."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field


class FailureCategory(StrEnum):
    """Supported failure root-cause categories."""

    ASSERTION_FAILURE = "assertion_failure"
    APPLICATION_ERROR = "application_error"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    LOCATOR_FAILURE = "locator_failure"
    NETWORK_FAILURE = "network_failure"
    TIMEOUT_FAILURE = "timeout_failure"
    UNKNOWN = "unknown"


class FailureClassification(BaseModel):
    """Structured classification result with supporting evidence."""

    category: FailureCategory
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    summary: str


class FailureClassifier:
    """Classifies test failures from tracebacks, browser console logs, and network failures."""

    @staticmethod
    def classify(
        error_message: str,
        stack_trace: str = "",
        console_logs: str = "",
        failed_network_requests: Sequence[dict[str, object]] = (),
    ) -> FailureClassification:
        """Analyze failure signals and return the highest-confidence root-cause category."""
        combined_text = f"{error_message}\n{stack_trace}".lower()
        console_lower = console_logs.lower()

        infra_markers = (
            "connection refused",
            "econnrefused",
            "apiconnectionerror",
            "service unavailable",
            "database unreachable",
            "targetclosederror",
            "browser has been closed",
        )
        if any(m in combined_text for m in infra_markers):
            return FailureClassification(
                category=FailureCategory.INFRASTRUCTURE_FAILURE,
                confidence=0.92,
                evidence=["Infrastructure or service connectivity marker found in error text"],
                summary="Target service or browser process was unreachable during execution.",
            )

        explicit_assertion_markers = (
            "assertionerror",
            "locator expected to ",
            "to_have_text",
            "to_contain_text",
        )
        if any(m in combined_text for m in explicit_assertion_markers) and (
            "resolved to 0 elements" not in combined_text
            and "strict mode violation" not in combined_text
            and "<element(s) not found>" not in combined_text
        ):
            return FailureClassification(
                category=FailureCategory.ASSERTION_FAILURE,
                confidence=0.88,
                evidence=["Explicit test assertion failure detected in traceback"],
                summary="Application behavior or response deviated from expected test assertion.",
            )

        locator_markers = (
            "waiting for locator(",
            "waiting for selector",
            "waiting for get_by_",
            "strict mode violation",
            "resolved to 0 elements",
            "<element(s) not found>",
            "element is not visible",
        )
        if any(m in combined_text for m in locator_markers):
            return FailureClassification(
                category=FailureCategory.LOCATOR_FAILURE,
                confidence=0.89,
                evidence=["Playwright locator resolution failure detected in stack trace"],
                summary="UI selector failed to resolve to a unique visible element.",
            )

        if "pageerror" in console_lower or "uncaught " in console_lower:
            return FailureClassification(
                category=FailureCategory.APPLICATION_ERROR,
                confidence=0.86,
                evidence=["Uncaught JavaScript runtime exception detected in browser console"],
                summary="Frontend application threw an unhandled JavaScript exception.",
            )

        if failed_network_requests:
            statuses = [
                req.get("status")
                for req in failed_network_requests
                if req.get("status") is not None
            ]
            if any(isinstance(s, int) and s >= 500 for s in statuses):
                return FailureClassification(
                    category=FailureCategory.NETWORK_FAILURE,
                    confidence=0.90,
                    evidence=[f"Captured HTTP 5xx network responses: {statuses}"],
                    summary="Backend returned HTTP 5xx error response during test execution.",
                )
            if any(
                "err_" in str(req.get("error_text", "")).lower() for req in failed_network_requests
            ):
                return FailureClassification(
                    category=FailureCategory.NETWORK_FAILURE,
                    confidence=0.88,
                    evidence=["Captured transport-level network failure in browser"],
                    summary="Network transport failure interrupted API or asset loading.",
                )

        if (
            "timeout" in combined_text
            or "timed out" in combined_text
            or "apitimeouterror" in combined_text
        ):
            return FailureClassification(
                category=FailureCategory.TIMEOUT_FAILURE,
                confidence=0.82,
                evidence=["Execution exceeded configured wait or request timeout"],
                summary="Operation timed out waiting for application state transition.",
            )

        assertion_markers = (
            "assert ",
            "expected ",
            "to_be_visible",
        )
        if any(m in combined_text for m in assertion_markers):
            return FailureClassification(
                category=FailureCategory.ASSERTION_FAILURE,
                confidence=0.85,
                evidence=["Test assertion mismatch detected in traceback"],
                summary="Application behavior or response deviated from expected test assertion.",
            )

        return FailureClassification(
            category=FailureCategory.UNKNOWN,
            confidence=0.40,
            evidence=["No deterministic failure pattern matched"],
            summary="Unclassified failure; inspect attached Playwright trace and logs.",
        )
