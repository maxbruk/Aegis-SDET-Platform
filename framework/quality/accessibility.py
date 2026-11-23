"""Automated accessibility testing engine with axe-core support, modal checks, and keyboard audits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Page

_DEFAULT_AXE_SCRIPT = Path(__file__).resolve().parent / "vendor" / "axe.min.js"

_DOM_AUDIT_SCRIPT = """
() => {
    const violations = [];

    const buildSelector = (el) => {
        if (el.id) return `#${el.id}`;
        const testId = el.getAttribute('data-testid');
        if (testId) return `[data-testid="${testId}"]`;
        return el.tagName.toLowerCase();
    };

    const isVisible = (el) => {
        if (el.closest('.hidden') || el.hasAttribute('hidden')) return false;
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden';
    };

    // Rule 1: Form controls must have explicit label/aria-label/aria-labelledby (placeholder is NOT valid)
    const formInputs = document.querySelectorAll('input, select, textarea');
    formInputs.forEach(input => {
        if (input.type === 'hidden') return;
        const id = input.id;
        const explicitLabel = id ? document.querySelector(`label[for="${id}"]`) : null;
        const wrappingLabel = input.closest('label');
        const hasLabelText = Boolean(
            (explicitLabel && explicitLabel.textContent.trim()) ||
            (wrappingLabel && wrappingLabel.textContent.trim())
        );
        const hasAriaName = Boolean(
            (input.getAttribute('aria-label') || '').trim() ||
            (input.getAttribute('aria-labelledby') || '').trim()
        );
        if (!hasLabelText && !hasAriaName) {
            violations.push({
                rule: 'label',
                impact: 'critical',
                severity: 'critical',
                selector: buildSelector(input),
                description: 'Form control has no associated label, aria-label, or aria-labelledby (placeholder alone is insufficient)',
                suggestion: 'Add a <label for="..."> element or non-empty aria-label/aria-labelledby attribute',
                element: input.outerHTML.substring(0, 120),
                help: 'Form input missing accessible label'
            });
        }
    });

    // Rule 2: Buttons must have accessible names
    const buttons = document.querySelectorAll('button, [role="button"]');
    buttons.forEach(btn => {
        const text = (btn.innerText || btn.textContent || '').trim();
        const ariaLabel = (btn.getAttribute('aria-label') || btn.getAttribute('aria-labelledby') || '').trim();
        if (!text && !ariaLabel) {
            violations.push({
                rule: 'button-name',
                impact: 'critical',
                severity: 'critical',
                selector: buildSelector(btn),
                description: 'Button has no accessible name',
                suggestion: 'Add visible button text or an aria-label attribute',
                element: btn.outerHTML.substring(0, 120),
                help: 'Button has no readable text or aria-label'
            });
        }
    });

    // Rule 3: Links must have accessible names
    const links = document.querySelectorAll('a');
    links.forEach(link => {
        const text = (link.innerText || link.textContent || '').trim();
        const ariaLabel = (link.getAttribute('aria-label') || '').trim();
        const img = link.querySelector('img[alt]');
        const imgAlt = img ? (img.getAttribute('alt') || '').trim() : '';
        if (!text && !ariaLabel && !imgAlt) {
            violations.push({
                rule: 'link-name',
                impact: 'serious',
                severity: 'serious',
                selector: buildSelector(link),
                description: 'Link has no discernible text or aria-label',
                suggestion: 'Add descriptive link text or an aria-label attribute',
                element: link.outerHTML.substring(0, 120),
                help: 'Link has no text or aria-label'
            });
        }
    });

    // Rule 4: Images must have alt text unless explicitly decorative
    const images = document.querySelectorAll('img');
    images.forEach(img => {
        const ariaHidden = img.getAttribute('aria-hidden') === 'true';
        const role = img.getAttribute('role');
        if (ariaHidden || role === 'presentation' || role === 'none') return;
        if (!img.hasAttribute('alt')) {
            violations.push({
                rule: 'image-alt',
                impact: 'serious',
                severity: 'serious',
                selector: buildSelector(img),
                description: 'Image element is missing an alt attribute',
                suggestion: 'Provide meaningful alt text or alt="" for decorative images',
                element: img.outerHTML.substring(0, 120),
                help: 'Image missing alt attribute'
            });
        }
    });

    // Rule 5: Duplicate element IDs
    const ids = new Set();
    const duplicateIds = new Set();
    document.querySelectorAll('[id]').forEach(el => {
        const id = el.id.trim();
        if (!id) return;
        if (ids.has(id)) {
            duplicateIds.add(id);
        } else {
            ids.add(id);
        }
    });
    duplicateIds.forEach(id => {
        violations.push({
            rule: 'duplicate-id',
            impact: 'moderate',
            severity: 'moderate',
            selector: `#${id}`,
            description: `Duplicate DOM id "${id}" breaks label and ARIA references`,
            suggestion: 'Ensure every id attribute in the document is unique',
            element: `#${id}`,
            help: `Duplicate ID detected in DOM: ${id}`
        });
    });

    // Rule 6: Visible modal dialogs must expose ARIA dialog semantics
    const visibleModals = document.querySelectorAll('.modal-backdrop:not(.hidden)');
    visibleModals.forEach(modal => {
        if (!isVisible(modal)) return;
        const role = modal.getAttribute('role');
        const ariaModal = modal.getAttribute('aria-modal');
        const hasTitle = Boolean(
            (modal.getAttribute('aria-label') || '').trim() ||
            (modal.getAttribute('aria-labelledby') || '').trim()
        );
        if (role !== 'dialog' || ariaModal !== 'true' || !hasTitle) {
            violations.push({
                rule: 'aria-dialog-name',
                impact: 'serious',
                severity: 'serious',
                selector: buildSelector(modal),
                description: 'Visible modal dialog is missing role="dialog", aria-modal="true", or accessible title',
                suggestion: 'Set role="dialog", aria-modal="true", and aria-label or aria-labelledby on the modal container',
                element: modal.outerHTML.substring(0, 120),
                help: 'Modal dialog lacks ARIA dialog attributes'
            });
        }
    });

    return {
        engine: 'aegis-builtin',
        passes: violations.length === 0,
        violation_count: violations.length,
        violations: violations
    };
}
"""

_MODAL_AUDIT_SCRIPT = """
(selector) => {
    const candidates = selector
        ? Array.from(document.querySelectorAll(selector))
        : Array.from(document.querySelectorAll('[role="dialog"], .modal-backdrop:not(.hidden), .cart-drawer.open'));
    const issues = [];

    candidates.forEach(modal => {
        const style = window.getComputedStyle(modal);
        if (modal.classList.contains('hidden') || style.display === 'none') return;

        const idSelector = modal.id ? `#${modal.id}` : `[data-testid="${modal.getAttribute('data-testid') || 'dialog'}"]`;
        if (modal.getAttribute('role') !== 'dialog') {
            issues.push({
                rule: 'dialog-role',
                impact: 'serious',
                severity: 'serious',
                selector: idSelector,
                description: 'Active modal or drawer is missing role="dialog"',
                suggestion: 'Add role="dialog" to the dialog container'
            });
        }
        if (modal.getAttribute('aria-modal') !== 'true') {
            issues.push({
                rule: 'dialog-aria-modal',
                impact: 'moderate',
                severity: 'moderate',
                selector: idSelector,
                description: 'Active modal or drawer is missing aria-modal="true"',
                suggestion: 'Add aria-modal="true" so assistive technologies restrict navigation to the dialog'
            });
        }
        const hasAccessibleTitle = Boolean(
            (modal.getAttribute('aria-label') || '').trim() ||
            (modal.getAttribute('aria-labelledby') || '').trim()
        );
        if (!hasAccessibleTitle) {
            issues.push({
                rule: 'dialog-accessible-name',
                impact: 'serious',
                severity: 'serious',
                selector: idSelector,
                description: 'Dialog has no aria-label or aria-labelledby attribute',
                suggestion: 'Provide an accessible dialog title using aria-labelledby or aria-label'
            });
        }
        const focusables = modal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])');
        if (focusables.length === 0) {
            issues.push({
                rule: 'dialog-focusable-element',
                impact: 'critical',
                severity: 'critical',
                selector: idSelector,
                description: 'Modal dialog contains no keyboard-focusable controls',
                suggestion: 'Ensure the dialog includes at least a focusable close or action button'
            });
        }
    });

    return issues;
}
"""


class AccessibilityAuditor:
    """Executes automated accessibility testing across DOM controls, modals, and keyboard focus."""

    def __init__(self, page: Page, axe_script_path: str | Path | None = None) -> None:
        self.page = page
        if axe_script_path is not None:
            self.axe_script_path: Path | None = Path(axe_script_path)
        else:
            self.axe_script_path = _DEFAULT_AXE_SCRIPT if _DEFAULT_AXE_SCRIPT.exists() else None

    def _run_axe_if_available(self) -> list[dict[str, Any]] | None:
        """Run axe-core when injected on the page or configured via axe_script_path."""
        if self.axe_script_path and self.axe_script_path.exists():
            has_axe = bool(self.page.evaluate("() => typeof window.axe !== 'undefined'"))
            if not has_axe:
                self.page.add_script_tag(path=str(self.axe_script_path))

        has_axe = bool(self.page.evaluate("() => typeof window.axe !== 'undefined'"))
        if not has_axe:
            return None

        raw_results = self.page.evaluate("async () => await window.axe.run(document)")
        normalized: list[dict[str, Any]] = []
        for violation in raw_results.get("violations", []):
            impact = violation.get("impact") or "serious"
            nodes = violation.get("nodes", [])
            node_targets = [
                ", ".join(str(part) for part in n.get("target", []))
                for n in nodes
                if n.get("target")
            ]
            selector = "; ".join(node_targets) if node_targets else "document"
            normalized.append(
                {
                    "rule": violation.get("id", "axe-rule"),
                    "impact": impact,
                    "severity": impact,
                    "selector": selector,
                    "description": violation.get("description", ""),
                    "suggestion": violation.get("help", ""),
                }
            )
        return normalized

    def run_audit(self) -> dict[str, Any]:
        """Run automated accessibility checks (axe-core when available + AEGIS DOM rules)."""
        builtin_result = self.page.evaluate(_DOM_AUDIT_SCRIPT)
        violations: list[dict[str, Any]] = list(builtin_result.get("violations", []))
        engine = "aegis-builtin"

        axe_violations = self._run_axe_if_available()
        if axe_violations is not None:
            engine = "axe-core+aegis"
            seen = {(v["rule"], v["selector"]) for v in violations}
            for item in axe_violations:
                key = (item["rule"], item["selector"])
                if key not in seen:
                    violations.append(item)
                    seen.add(key)

        return {
            "engine": engine,
            "automated_testing_note": (
                "Automated accessibility testing detects common structural/ARIA issues; "
                "it does not constitute full manual WCAG 2.1 AA certification."
            ),
            "passes": len(violations) == 0,
            "violation_count": len(violations),
            "violations": violations,
        }

    def audit_page(self) -> list[dict[str, Any]]:
        """Audit current page DOM and return structured violation records."""
        res = self.run_audit()
        violations: list[dict[str, Any]] = res.get("violations", [])
        for v in violations:
            v.setdefault("severity", v.get("impact", "critical"))
        return violations

    def check_modal_accessibility(self, modal_selector: str | None = None) -> list[dict[str, Any]]:
        """Validate ARIA dialog semantics and focusable elements on visible modals/drawers."""
        return list(self.page.evaluate(_MODAL_AUDIT_SCRIPT, modal_selector))

    def check_keyboard_navigation(self, steps: int = 5, min_distinct: int = 2) -> dict[str, Any]:
        """Press Tab sequentially and verify focus moves across distinct interactive controls."""
        visited: list[str] = []
        for _ in range(steps):
            self.page.keyboard.press("Tab")
            active = self.page.evaluate(
                """
                () => {
                    const el = document.activeElement;
                    if (!el || el === document.body || el === document.documentElement) return null;
                    if (el.id) return `#${el.id}`;
                    const testId = el.getAttribute('data-testid');
                    if (testId) return `[data-testid="${testId}"]`;
                    return el.tagName.toLowerCase();
                }
                """
            )
            if active:
                visited.append(active)

        unique_visited = list(dict.fromkeys(visited))
        required = min(steps, min_distinct) if steps > 0 else 0
        return {
            "passed": len(unique_visited) >= required,
            "steps_attempted": steps,
            "visited_count": len(unique_visited),
            "visited_selectors": unique_visited,
        }
