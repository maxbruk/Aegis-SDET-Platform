"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from typing import Any

from framework.api.client import APIResponse, BaseAPIClient
from framework.api.models.order_models import CheckoutRequest


class OrdersAPI:
    """Encapsulates /api/v1/orders endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client

    def checkout(
        self,
        request_data: CheckoutRequest | dict[str, Any],
        idempotency_key: str | None = None,
    ) -> APIResponse:
        """Execute ACID order checkout transaction with optional Idempotency-Key."""
        payload = (
            request_data.model_dump(exclude_none=True)
            if isinstance(request_data, CheckoutRequest)
            else request_data
        )
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        return self.client.post("/api/v1/orders/checkout", json_data=payload, headers=headers)

    def get_orders(self) -> APIResponse:
        """Retrieve order history for authenticated user."""
        return self.client.get("/api/v1/orders")

    def get_order(self, order_id: int) -> APIResponse:
        """Retrieve details for a single order."""
        return self.client.get(f"/api/v1/orders/{order_id}")

    def delete_order(self, order_id: int) -> APIResponse:
        """Delete an order by database ID (Admin or owning user)."""
        return self.client.delete(f"/api/v1/orders/{order_id}")
