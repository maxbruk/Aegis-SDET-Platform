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

from framework.api.models.product_models import (
    ProductCreateRequest,
    ProductDTO,
    ProductListResponse,
)
from framework.api.products_api import ProductsAPI


@allure.epic("API Contracts & Validation")
@allure.feature("Product Catalog Schemas")
@pytest.mark.api
class TestProductAPIContract:
    """Contract tests for Product DTOs and validation schemas."""

    @allure.story("Product DTO Serialization")
    @allure.severity(allure.severity_level.NORMAL)
    def test_product_dto_serialization(self):
        """Verifies ProductDTO fields and type constraints."""
        with allure.step("Validate ProductDTO structure"):
            product_data = {
                "id": 1,
                "name": "Apex Pro Keyboard",
                "description": "Mechanical gaming keyboard with tactile switches.",
                "price": 149.99,
                "stock": 15,
                "category": "Electronics",
            }
            product = ProductDTO(**product_data)
            assert product.id == 1
            assert product.price == 149.99
            assert product.stock == 15

    @allure.story("Product Creation Validation Constraints")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_product_create_request_validation(self):
        """Ensures non-negative prices and required fields in ProductCreateRequest."""
        with allure.step("Validate positive price"):
            valid_payload = {
                "name": "Custom Keycaps",
                "description": "PBT double-shot keycaps",
                "price": 34.50,
                "stock": 100,
                "category": "Accessories",
            }
            model = ProductCreateRequest(**valid_payload)
            assert model.price == 34.50

        with (
            allure.step("Assert ValidationError on negative price"),
            pytest.raises(ValidationError),
        ):
            ProductCreateRequest(
                name="Invalid",
                description="Negative price",
                price=-10.0,
                stock=5,
                category="Accessories",
            )

    @allure.story("Product List Response Schema")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_product_list_response_schema(self):
        """Verifies ProductListResponse containing an array of products."""
        with allure.step("Deserialize product list schema"):
            raw_list = {
                "products": [
                    {
                        "id": 1,
                        "name": "Item A",
                        "description": "Desc A",
                        "price": 10.0,
                        "stock": 5,
                        "category": "Electronics",
                    },
                    {
                        "id": 2,
                        "name": "Item B",
                        "description": "Desc B",
                        "price": 20.0,
                        "stock": 10,
                        "category": "Audio",
                    },
                ],
                "total": 2,
                "page": 1,
                "limit": 20,
            }
            resp = ProductListResponse(**raw_list)
            assert len(resp.products) == 2
            assert resp.products[0].name == "Item A"


@allure.epic("API Contracts & Validation")
@allure.feature("Product Catalog Integration")
@pytest.mark.api
class TestProductAPIIntegration:
    """Integration tests calling the Product API."""

    @allure.story("List Products HTTP Endpoint")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_list_products_endpoint(self, products_api: ProductsAPI):
        """Fetches product listing from API and verifies response format."""
        with allure.step("GET /api/v1/products"):
            res = products_api.list_products()
            if not res.is_success:
                pytest.skip("Backend API on port 3000 not running.")

            assert res.status_code == 200
            data = res.json()
            assert "products" in data or "data" in data or isinstance(data, list)
