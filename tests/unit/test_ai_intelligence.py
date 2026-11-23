"""Unit tests for AI Failure Intelligence: classification, healing validation, audit, and history."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.ai.analyzer import FailureIntelligenceAnalyzer
from framework.ai.classifier import FailureCategory, FailureClassifier
from framework.ai.history import HistoricalFailureStore, redact_sensitive_text
from framework.ai.locator_healer import LocatorHealer, LocatorValidationEngine
from framework.execution.run_context import RunContext


@pytest.mark.unit
class TestAIFailureIntelligence:
    """Verifies failure categorization, locator healing validation, audit trail, and history."""

    def test_classifier_identifies_network_locator_and_assertion_failures(self) -> None:
        net_res = FailureClassifier.classify(
            error_message="Checkout request failed",
            failed_network_requests=[{"status": 500, "url": "/api/v1/orders/checkout"}],
        )
        assert net_res.category == FailureCategory.NETWORK_FAILURE

        loc_res = FailureClassifier.classify(
            error_message='TimeoutError: waiting for locator("button.checkout-old")',
        )
        assert loc_res.category == FailureCategory.LOCATOR_FAILURE

        assert_res = FailureClassifier.classify(
            error_message="AssertionError: Expected 6 products, found 5",
        )
        assert assert_res.category == FailureCategory.ASSERTION_FAILURE

        expect_res = FailureClassifier.classify(
            error_message='AssertionError: Locator expected to have text "API Live" waiting for locator("#api-status")',
            failed_network_requests=[{"status": 500, "url": "/stale"}],
        )
        assert expect_res.category == FailureCategory.ASSERTION_FAILURE

        missing_expect_res = FailureClassifier.classify(
            error_message=(
                "AssertionError: Locator expected to be visible\n"
                "Actual value: <element(s) not found>\n"
                'Call log:\n  - waiting for get_by_test_id("old-checkout")'
            ),
        )
        assert missing_expect_res.category == FailureCategory.LOCATOR_FAILURE

    def test_void_input_elements_do_not_corrupt_parser_text_and_secrets_redacted(self) -> None:
        html_snippet = """
        <button id="wrap">
          <input id="search" type="text" placeholder="Search">
          <span>Checkout Now</span>
        </button>
        """
        elements = LocatorHealer.parse_dom_elements(html_snippet)
        button_snap = next(e for e in elements if e.tag == "button")
        input_snap = next(e for e in elements if e.tag == "input")
        assert "Checkout Now" in button_snap.text
        assert input_snap.text == ""

        redacted = redact_sensitive_text(
            "Header Authorization: Bearer secret.jwt.token password=MySecret123!"
        )
        assert "secret.jwt.token" not in redacted
        assert "MySecret123" not in redacted
        assert "[REDACTED]" in redacted

    def test_locator_healer_and_validation_engine_reject_ambiguous_and_approve_unique(self) -> None:
        dom_html = """
        <div>
          <button data-testid="checkout-submit" id="checkout-submit">Checkout</button>
          <button class="dup-btn">Duplicate</button>
          <button class="dup-btn">Duplicate</button>
        </div>
        """
        candidates = LocatorHealer.suggest_candidates('locator("button.checkout-submit")', dom_html)
        assert len(candidates) >= 1
        assert candidates[0].playwright_expression == 'page.get_by_test_id("checkout-submit")'

        valid_result = LocatorValidationEngine.validate_against_html(candidates[0], dom_html)
        assert valid_result.validation_status == "validated"
        assert valid_result.match_count == 1

        # Ambiguous button text matching 2 elements must be rejected
        ambiguous_candidates = LocatorHealer.suggest_candidates(
            'locator("button.duplicate")', dom_html
        )
        assert len(ambiguous_candidates) == 1
        rejected_result = LocatorValidationEngine.validate_against_html(
            ambiguous_candidates[0], dom_html
        )
        assert rejected_result.validation_status == "rejected"
        assert rejected_result.match_count == 2

    def test_analyzer_creates_audit_trail_history_match_and_never_passes_failed_test(
        self, tmp_path: Path
    ) -> None:
        run_ctx = RunContext(run_id="run-ai-001", runs_root=tmp_path / "runs")
        history_store = HistoricalFailureStore(history_path=tmp_path / "failure_history.jsonl")
        history_store.record_failure(
            run_id="run-ai-000",
            test_id="tests/ui/test_checkout.py::test_submit",
            category="locator_failure",
            error_message='TimeoutError: waiting for locator("#old-checkout-btn") on checkout modal',
        )

        dom_html = '<button data-testid="checkout-btn">Proceed</button>'
        analyzer = FailureIntelligenceAnalyzer(run_context=run_ctx, history_store=history_store)
        report = analyzer.analyze_failure(
            test_id="tests/ui/test_checkout.py::test_submit",
            error_message='TimeoutError: waiting for locator("#old-checkout-btn") on checkout modal',
            dom_html=dom_html,
        )

        assert report.test_status == "failed"
        assert report.classification.category == FailureCategory.LOCATOR_FAILURE
        assert report.locator_audit is not None
        assert report.locator_audit.suggested_locator == 'page.get_by_test_id("checkout-btn")'
        assert report.locator_audit.validation_status == "validated"
        assert report.locator_audit.approval_status == "pending_human_approval"
        assert len(report.similar_historical_failures) >= 1
        assert report.similar_historical_failures[0].run_id == "run-ai-000"
        saved_files = list(run_ctx.ai_diagnostics_dir.glob("ai_*.json"))
        assert len(saved_files) == 1

    def test_analyzer_extracts_testid_and_falls_back_to_validated_candidate(
        self, tmp_path: Path
    ) -> None:
        assert (
            LocatorHealer.extract_failed_locator('TimeoutError: get_by_test_id("old-submit")')
            == 'get_by_test_id("old-submit")'
        )
        dom_html = """
        <div>
          <button data-testid="submit-dup">Dup</button>
          <button data-testid="submit-dup">Dup</button>
          <button id="submit-order">Proceed Order</button>
        </div>
        """
        run_ctx = RunContext(run_id="run-ai-002", runs_root=tmp_path / "runs")
        history_store = HistoricalFailureStore(history_path=tmp_path / "failure_history.jsonl")
        report = FailureIntelligenceAnalyzer(
            run_context=run_ctx, history_store=history_store
        ).analyze_failure(
            test_id="tests/ui/test_checkout.py::test_fallback",
            error_message='TimeoutError: waiting for get_by_test_id("submit-order")',
            dom_html=dom_html,
        )
        assert report.locator_audit is not None
        assert report.locator_audit.validation_status == "validated"
        assert report.locator_audit.suggested_locator == 'page.locator("#submit-order")'
        assert report.locator_audit.approval_status == "pending_human_approval"
