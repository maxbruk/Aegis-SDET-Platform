"""DOM-aware locator suggestion, uniqueness validation, and audit trail."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import TYPE_CHECKING, ClassVar, Literal

from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from playwright.sync_api import Page


class DOMElementSnapshot(BaseModel):
    """Lightweight representation of an interactive DOM element."""

    tag: str
    attrs: dict[str, str] = Field(default_factory=dict)
    text: str = ""


class LocatorCandidate(BaseModel):
    """Suggested replacement locator produced by LocatorHealer."""

    selector: str
    playwright_expression: str
    strategy: str
    match_value: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class LocatorValidationResult(BaseModel):
    """Result of checking candidate uniqueness and semantic compatibility."""

    candidate: LocatorCandidate
    validation_status: Literal["validated", "rejected"]
    match_count: int = Field(ge=0)
    probe_passed: bool = False
    reason: str


class HealingAuditRecord(BaseModel):
    """Audit trail entry requiring human review before any test locator is modified."""

    test_id: str
    failed_locator: str
    suggested_locator: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_status: Literal["validated", "rejected", "not_attempted"]
    probe_passed: bool = False
    approval_status: Literal["pending_human_approval", "rejected"]
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    explanation: str


class _InteractiveDOMParser(HTMLParser):
    _INTERACTIVE_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"button", "input", "select", "textarea", "a"}
    )
    _VOID_TAGS: ClassVar[frozenset[str]] = frozenset({"input", "img", "br", "hr", "meta", "link"})

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[DOMElementSnapshot] = []
        self._stack: list[DOMElementSnapshot] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        is_interactive = (
            tag in self._INTERACTIVE_TAGS
            or "data-testid" in attr_map
            or attr_map.get("role") in {"button", "link", "textbox"}
        )
        if is_interactive:
            snap = DOMElementSnapshot(tag=tag, attrs=attr_map)
            self.elements.append(snap)
            if tag not in self._VOID_TAGS:
                self._stack.append(snap)

    def handle_data(self, data: str) -> None:
        if self._stack:
            text = data.strip()
            if text:
                existing = self._stack[-1].text
                self._stack[-1].text = f"{existing} {text}".strip()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._VOID_TAGS:
            return
        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx].tag == tag:
                del self._stack[idx:]
                break


def _tokenize(raw: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-z0-9]+", raw.lower()) if len(tok) >= 2}


class LocatorHealer:
    """Suggests alternative semantic/test-id locators from a DOM snapshot."""

    @staticmethod
    def extract_failed_locator(error_message: str) -> str | None:
        """Extract selector or semantic get_by_* expression from a Playwright error string."""
        match = re.search(r"locator\((['\"])(.+?)\1\)", error_message)
        if match:
            return match.group(2)
        for fn_name in (
            "get_by_test_id",
            "get_by_label",
            "get_by_text",
            "get_by_placeholder",
            "get_by_role",
        ):
            semantic_match = re.search(rf"{fn_name}\([^)]+\)", error_message)
            if semantic_match:
                return semantic_match.group(0)
        return None

    @staticmethod
    def parse_dom_elements(html_content: str) -> list[DOMElementSnapshot]:
        parser = _InteractiveDOMParser()
        parser.feed(html_content)
        return parser.elements

    @classmethod
    def suggest_candidates(
        cls,
        failed_locator: str,
        html_content: str,
        max_candidates: int = 3,
    ) -> list[LocatorCandidate]:
        """Rank candidate locators from DOM elements sharing tokens with failed_locator."""
        target_tokens = _tokenize(failed_locator)
        elements = cls.parse_dom_elements(html_content)
        scored: list[tuple[float, LocatorCandidate]] = []

        for elem in elements:
            attrs = elem.attrs
            searchable = " ".join(
                [
                    attrs.get("data-testid", ""),
                    attrs.get("id", ""),
                    attrs.get("aria-label", ""),
                    attrs.get("name", ""),
                    elem.text,
                ]
            )
            elem_tokens = _tokenize(searchable)
            overlap = len(target_tokens & elem_tokens)
            if target_tokens and overlap == 0:
                continue

            if attrs.get("data-testid"):
                testid = attrs["data-testid"]
                cand = LocatorCandidate(
                    selector=f'[data-testid="{testid}"]',
                    playwright_expression=f'page.get_by_test_id("{testid}")',
                    strategy="data-testid",
                    match_value=testid,
                    confidence=min(0.95, 0.72 + 0.08 * overlap),
                    rationale=f"Stable data-testid attribute matches target intent ({overlap} shared tokens).",
                )
            elif attrs.get("aria-label"):
                label = attrs["aria-label"]
                cand = LocatorCandidate(
                    selector=f'{elem.tag}[aria-label="{label}"]',
                    playwright_expression=f'page.locator("{elem.tag}[aria-label=\\"{label}\\"]")',
                    strategy="aria-label",
                    match_value=label,
                    confidence=min(0.88, 0.65 + 0.08 * overlap),
                    rationale=f"Accessible aria-label matches target intent ({overlap} shared tokens).",
                )
            elif attrs.get("id"):
                elem_id = attrs["id"]
                cand = LocatorCandidate(
                    selector=f"#{elem_id}",
                    playwright_expression=f'page.locator("#{elem_id}")',
                    strategy="id",
                    match_value=elem_id,
                    confidence=min(0.84, 0.60 + 0.08 * overlap),
                    rationale=f"Unique id attribute matches target intent ({overlap} shared tokens).",
                )
            elif elem.text and elem.tag == "button":
                cand = LocatorCandidate(
                    selector=f'button:has-text("{elem.text}")',
                    playwright_expression=f'page.get_by_role("button", name="{elem.text}")',
                    strategy="role-name",
                    match_value=elem.text,
                    confidence=min(0.82, 0.58 + 0.08 * overlap),
                    rationale=f"Button accessible text matches target intent ({overlap} shared tokens).",
                )
            else:
                continue

            scored.append((cand.confidence, cand))

        scored.sort(key=lambda item: item[0], reverse=True)
        seen: set[str] = set()
        results: list[LocatorCandidate] = []
        for _, cand in scored:
            if cand.selector in seen:
                continue
            seen.add(cand.selector)
            results.append(cand)
            if len(results) >= max_candidates:
                break
        return results


class LocatorValidationEngine:
    """Verifies that a suggested locator uniquely resolves before proposing it for approval."""

    @staticmethod
    def validate_against_html(
        candidate: LocatorCandidate,
        html_content: str,
    ) -> LocatorValidationResult:
        """Offline DOM uniqueness validation using parsed attributes."""
        elements = LocatorHealer.parse_dom_elements(html_content)
        count = 0
        if candidate.strategy == "data-testid":
            val = candidate.match_value or candidate.selector.split('"')[1]
            count = sum(1 for e in elements if e.attrs.get("data-testid") == val)
        elif candidate.strategy == "id":
            val = candidate.match_value or candidate.selector.lstrip("#")
            count = sum(1 for e in elements if e.attrs.get("id") == val)
        elif candidate.strategy == "aria-label":
            val = candidate.match_value or candidate.selector.split('"')[1]
            count = sum(1 for e in elements if e.attrs.get("aria-label") == val)
        elif candidate.strategy == "role-name":
            val = candidate.match_value or candidate.selector.split('"')[1]
            count = sum(1 for e in elements if e.tag == "button" and val in e.text)

        if count == 1:
            return LocatorValidationResult(
                candidate=candidate,
                validation_status="validated",
                match_count=1,
                reason="Candidate uniquely matches exactly 1 DOM element.",
            )
        return LocatorValidationResult(
            candidate=candidate,
            validation_status="rejected",
            match_count=count,
            reason=f"Candidate rejected because it matched {count} elements (must equal 1).",
        )

    @staticmethod
    def validate_against_page(
        candidate: LocatorCandidate,
        page: Page,
    ) -> LocatorValidationResult:
        """Live Playwright uniqueness and actionability probe against the rendered DOM."""
        try:
            locator = page.locator(candidate.selector)
            count = locator.count()
        except (PlaywrightError, RuntimeError) as exc:
            return LocatorValidationResult(
                candidate=candidate,
                validation_status="rejected",
                match_count=0,
                probe_passed=False,
                reason=f"Live DOM check failed: {exc}",
            )
        if count == 1:
            probe_ok = False
            try:
                probe_ok = bool(locator.first.is_visible() and locator.first.is_enabled())
            except (PlaywrightError, RuntimeError):
                probe_ok = False
            return LocatorValidationResult(
                candidate=candidate,
                validation_status="validated" if probe_ok else "rejected",
                match_count=1,
                probe_passed=probe_ok,
                reason=(
                    "Live page locator uniquely matches 1 visible and enabled element."
                    if probe_ok
                    else "Live locator matched 1 element but failed visibility/enabled probe."
                ),
            )
        return LocatorValidationResult(
            candidate=candidate,
            validation_status="rejected",
            match_count=count,
            probe_passed=False,
            reason=f"Live page locator matched {count} elements (must equal 1).",
        )
