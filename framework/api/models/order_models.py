"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from pydantic import BaseModel, ConfigDict, Field


class OrderItemDTO(BaseModel):
    """Line item in an order."""

    model_config = ConfigDict(extra="ignore")

    product_id: int
    product_name: str | None = None
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0.0)
    total_price: float | None = None


class CheckoutRequest(BaseModel):
    """Payload for POST /api/v1/orders/checkout."""

    shipping_address: str = Field(min_length=5, max_length=255)
    payment_method: str | None = "credit_card"
    idempotency_key: str | None = None


class OrderResponse(BaseModel):
    """Response returned upon successful order placement."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    order_id: str | None = None
    user_id: int | None = None
    status: str
    total_amount: float = Field(ge=0.0)
    items_count: int | None = None
    idempotency_key: str | None = None
    created_at: str | None = None
    items: list[OrderItemDTO] = []
