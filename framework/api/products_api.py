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
from framework.api.models.product_models import (
    ProductCreateRequest,
    ProductUpdateRequest,
)


class ProductsAPI:
    """Encapsulates /api/v1/products endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client

    def list_products(
        self,
        category: str | None = None,
        search: str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> APIResponse:
        """List products with optional filtering."""
        params = {}
        if category:
            params["category"] = category
        if search:
            params["search"] = search
        if page:
            params["page"] = page
        if limit:
            params["limit"] = limit

        return self.client.get("/api/v1/products", params=params)

    def get_product(self, product_id: int) -> APIResponse:
        """Get product details by ID."""
        return self.client.get(f"/api/v1/products/{product_id}")

    def create_product(self, request_data: ProductCreateRequest | dict[str, Any]) -> APIResponse:
        """Create a new product (Admin RBAC required)."""
        payload = (
            request_data.model_dump()
            if isinstance(request_data, ProductCreateRequest)
            else request_data
        )
        return self.client.post("/api/v1/products", json_data=payload)

    def update_product(
        self, product_id: int, request_data: ProductUpdateRequest | dict[str, Any]
    ) -> APIResponse:
        """Update an existing product (Admin RBAC required)."""
        payload = (
            request_data.model_dump(exclude_none=True)
            if isinstance(request_data, ProductUpdateRequest)
            else request_data
        )
        return self.client.put(f"/api/v1/products/{product_id}", json_data=payload)

    def delete_product(self, product_id: int) -> APIResponse:
        """Delete a product by ID (Admin RBAC required)."""
        return self.client.delete(f"/api/v1/products/{product_id}")
