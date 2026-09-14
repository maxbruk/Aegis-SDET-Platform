"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from pydantic import BaseModel, ConfigDict, Field


class CartItemDTO(BaseModel):
    """Item inside shopping cart."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    product_id: int
    product_name: str | None = None
    name: str | None = None
    price: float | None = None
    quantity: int = Field(gt=0)
    subtotal: float | None = None
    stock: int | None = None


class AddToCartRequest(BaseModel):
    """Payload for POST /api/v1/cart/items."""

    product_id: int
    quantity: int = Field(gt=0, default=1)


class UpdateCartItemRequest(BaseModel):
    """Payload for PUT /api/v1/cart/items/{productId}."""

    quantity: int = Field(ge=0)


class CartResponse(BaseModel):
    """Response returned for GET /api/v1/cart."""

    model_config = ConfigDict(extra="ignore")

    items: list[CartItemDTO]
    total_items: int | None = 0
    subtotal: float | None = 0.0
    tax: float | None = 0.0
    total: float | None = 0.0
