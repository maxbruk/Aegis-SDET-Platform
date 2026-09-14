"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import uuid

import allure
import pytest

from framework.api.models.order_models import CheckoutRequest, OrderResponse


@allure.epic("API Contracts & Validation")
@allure.feature("Order Checkout & Idempotency Schemas")
@pytest.mark.api
class TestOrdersAPIContract:
    """Contract tests for Order checkout and Idempotency schemas."""

    @allure.story("Checkout Request Schema Validation")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_checkout_request_schema(self):
        """Verifies CheckoutRequest initializes valid shipping and payment details."""
        with allure.step("Validate valid CheckoutRequest"):
            payload = {
                "shipping_address": "1 Infinite Loop, Cupertino, CA",
                "payment_method": "credit_card",
                "idempotency_key": "idem-uuid-test-1234",
            }
            req = CheckoutRequest(**payload)
            assert req.shipping_address == "1 Infinite Loop, Cupertino, CA"
            assert req.payment_method == "credit_card"
            assert req.idempotency_key == "idem-uuid-test-1234"

    @allure.story("Order Response Schema Deserialization")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_order_response_schema(self):
        """Verifies OrderResponse schema deserialization and status validation."""
        with allure.step("Deserialize full OrderResponse model"):
            raw_order = {
                "order_id": "ORD-998811",
                "user_id": 42,
                "status": "COMPLETED",
                "total_amount": 161.99,
                "items_count": 1,
                "idempotency_key": "idem-uuid-test-1234",
                "created_at": "2026-08-30T12:00:00Z",
            }
            order = OrderResponse(**raw_order)
            assert order.order_id == "ORD-998811"
            assert order.status == "COMPLETED"
            assert order.total_amount == 161.99

    @allure.story("Idempotency-Key Header UUID Format")
    @allure.severity(allure.severity_level.NORMAL)
    def test_idempotency_key_header_generation(self):
        """Ensures generated idempotency keys are non-empty valid unique identifiers."""
        with allure.step("Generate dynamic UUID v4 Idempotency key"):
            key = f"idem-{uuid.uuid4()}"
            assert key.startswith("idem-")
            assert len(key) >= 36
