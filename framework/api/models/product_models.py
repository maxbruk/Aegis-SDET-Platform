"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from pydantic import BaseModel, ConfigDict, Field


class ProductDTO(BaseModel):
    """Product entity representation."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    description: str
    price: float = Field(ge=0.0)
    stock: int = Field(ge=0)
    category: str
    created_at: str | None = None


class ProductCreateRequest(BaseModel):
    """Payload for POST /api/v1/products."""

    name: str = Field(min_length=1, max_length=255)
    description: str
    price: float = Field(gt=0.0)
    stock: int = Field(ge=0)
    category: str = Field(min_length=1)


class ProductUpdateRequest(BaseModel):
    """Payload for PUT /api/v1/products/{id}."""

    name: str | None = None
    description: str | None = None
    price: float | None = Field(default=None, gt=0.0)
    stock: int | None = Field(default=None, ge=0)
    category: str | None = None


class ProductListResponse(BaseModel):
    """Response returned for GET /api/v1/products."""

    model_config = ConfigDict(extra="ignore")

    products: list[ProductDTO]
    total: int | None = None
    page: int | None = 1
    limit: int | None = 20
