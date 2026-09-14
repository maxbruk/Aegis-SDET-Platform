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
from pydantic import ValidationError

from framework.api.models.cart_models import (
    AddToCartRequest,
    CartResponse,
    UpdateCartItemRequest,
)


@allure.epic("API Contracts & Validation")
@allure.feature("Shopping Cart Schemas")
@pytest.mark.api
class TestCartAPIContract:
    """Contract and schema validation tests for Shopping Cart."""

    @allure.story("Add To Cart Schema Constraints")
    @allure.severity(allure.severity_level.NORMAL)
    def test_add_to_cart_request_validation(self):
        """Verifies quantity constraints on AddToCartRequest."""
        with allure.step("Validate quantity > 0 constraint"):
            req = AddToCartRequest(product_id=1, quantity=2)
            assert req.product_id == 1
            assert req.quantity == 2

            with pytest.raises(ValidationError):
                AddToCartRequest(product_id=1, quantity=0)

    @allure.story("Update Cart Item Constraints")
    @allure.severity(allure.severity_level.NORMAL)
    def test_update_cart_request_validation(self):
        """Verifies non-negative quantity constraints on UpdateCartItemRequest."""
        with allure.step("Validate non-negative quantity constraint"):
            req = UpdateCartItemRequest(quantity=0)
            assert req.quantity == 0

            with pytest.raises(ValidationError):
                UpdateCartItemRequest(quantity=-1)

    @allure.story("Cart Response Schema Deserialization")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_cart_response_schema_deserialization(self):
        """Validates that nested cart items and subtotal calculate correctly in CartResponse."""
        with allure.step("Deserialize full CartResponse model"):
            raw_cart = {
                "items": [
                    {
                        "product_id": 1,
                        "name": "Apex Keyboard",
                        "price": 149.99,
                        "quantity": 2,
                        "subtotal": 299.98,
                    },
                    {
                        "product_id": 2,
                        "name": "Precision Mouse",
                        "price": 79.99,
                        "quantity": 1,
                        "subtotal": 79.99,
                    },
                ],
                "subtotal": 379.97,
                "tax": 30.40,
                "total": 410.37,
            }
            cart = CartResponse(**raw_cart)
            assert len(cart.items) == 2
            assert cart.items[0].product_id == 1
            assert cart.items[0].subtotal == 299.98
            assert cart.total == 410.37
