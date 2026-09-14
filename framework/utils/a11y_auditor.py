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


class AccessibilityAuditor:
    """Executes automated accessibility rule checks across the DOM."""

    def __init__(self, page: Page):
        self.page = page

    def run_audit(self) -> dict[str, Any]:
        """Runs a comprehensive suite of WCAG 2.1 accessibility heuristics."""
        audit_script = """
        () => {
            const violations = [];

            // Rule 1: Form controls must have associated labels or aria-labels
            const formInputs = document.querySelectorAll('input, select, textarea');
            formInputs.forEach(input => {
                if (input.type === 'hidden') return;
                const id = input.id;
                const hasLabel = id && document.querySelector(`label[for="${id}"]`);
                const hasAriaLabel = input.getAttribute('aria-label') || input.getAttribute('aria-labelledby') || input.placeholder;
                if (!hasLabel && !hasAriaLabel) {
                    violations.push({
                        rule: 'form-control-has-label',
                        impact: 'critical',
                        element: input.outerHTML.substring(0, 100),
                        help: 'Form input missing label or aria-label'
                    });
                }
            });

            // Rule 2: Buttons must have accessible text
            const buttons = document.querySelectorAll('button, [role="button"]');
            buttons.forEach(btn => {
                const text = (btn.innerText || '').trim();
                const ariaLabel = btn.getAttribute('aria-label') || btn.getAttribute('title');
                if (!text && !ariaLabel) {
                    violations.push({
                        rule: 'button-has-accessible-name',
                        impact: 'serious',
                        element: btn.outerHTML.substring(0, 100),
                        help: 'Button has no readable text or aria-label'
                    });
                }
            });

            // Rule 3: Interactive elements must have semantic tags or roles
            const links = document.querySelectorAll('a');
            links.forEach(link => {
                const text = (link.innerText || '').trim();
                const ariaLabel = link.getAttribute('aria-label');
                if (!text && !ariaLabel && !link.querySelector('svg, img')) {
                    violations.push({
                        rule: 'link-has-accessible-name',
                        impact: 'moderate',
                        element: link.outerHTML.substring(0, 100),
                        help: 'Link has no text or aria-label'
                    });
                }
            });

            // Rule 4: Duplicate element IDs
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
                    rule: 'duplicate-id-active',
                    impact: 'minor',
                    element: `#${id}`,
                    help: `Duplicate ID detected in DOM: ${id}`
                });
            });

            return {
                passes: violations.length === 0,
                violation_count: violations.length,
                violations: violations
            };
        }
        """
        return self.page.evaluate(audit_script)

    def audit_page(self) -> list[dict[str, Any]]:
        """Audits current page DOM and returns list of violation records with severity tags."""
        res = self.run_audit()
        violations = res.get("violations", [])
        for v in violations:
            v["severity"] = v.get("impact", "critical")
        return violations
