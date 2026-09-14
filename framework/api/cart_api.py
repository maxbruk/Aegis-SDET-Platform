"""Shopping Cart API Client."""

from typing import Any

"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from framework.api.client import APIResponse, BaseAPIClient
from framework.api.models.cart_models import (
    AddToCartRequest,
    UpdateCartItemRequest,
)


class CartAPI:
    """Encapsulates /api/v1/cart endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client

    def get_cart(self) -> APIResponse:
        """Get current user's active cart."""
        return self.client.get("/api/v1/cart")

    def add_item(self, request_data: AddToCartRequest | dict[str, Any]) -> APIResponse:
        """Add an item to the shopping cart."""
        payload = (
            request_data.model_dump()
            if isinstance(request_data, AddToCartRequest)
            else request_data
        )
        return self.client.post("/api/v1/cart/items", json_data=payload)

    def update_quantity(
        self, product_id: int, request_data: UpdateCartItemRequest | dict[str, Any]
    ) -> APIResponse:
        """Update item quantity in cart."""
        payload = (
            request_data.model_dump()
            if isinstance(request_data, UpdateCartItemRequest)
            else request_data
        )
        return self.client.put(f"/api/v1/cart/items/{product_id}", json_data=payload)

    def remove_item(self, product_id: int) -> APIResponse:
        """Remove a specific item from cart."""
        return self.client.delete(f"/api/v1/cart/items/{product_id}")

    def clear_cart(self) -> APIResponse:
        """Empty the user's cart."""
        return self.client.delete("/api/v1/cart")
