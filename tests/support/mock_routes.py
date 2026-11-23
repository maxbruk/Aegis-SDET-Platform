"""Deterministic Playwright route mocks for backend-independent UI tests."""

import json

from playwright.sync_api import Page

MOCK_PRODUCTS = [
    {
        "id": 1,
        "name": "Apex Pro Mechanical Keyboard",
        "category": "Electronics",
        "price": 149.99,
        "stock": 15,
        "description": "Aircraft-grade aluminum frame, hot-swappable tactile switches, and PBT double-shot keycaps.",
    },
    {
        "id": 2,
        "name": "Precision Ergonomic Mouse",
        "category": "Electronics",
        "price": 79.99,
        "stock": 24,
        "description": "4000 DPI optical sensor, ultra-low latency wireless, and contoured thumb rest.",
    },
    {
        "id": 3,
        "name": "Studio Reference Headphones",
        "category": "Audio",
        "price": 249.99,
        "stock": 8,
        "description": "Open-back planar magnetic drivers delivering ultra-wide soundstage and neutral frequency response.",
    },
    {
        "id": 4,
        "name": "USB-C Braided Thunderbolt Cable",
        "category": "Accessories",
        "price": 29.99,
        "stock": 50,
        "description": "40Gbps data throughput and 100W Power Delivery with reinforced nylon braiding.",
    },
    {
        "id": 5,
        "name": "Solid Walnut Desk Mat (Extended)",
        "category": "Workspace",
        "price": 64.99,
        "stock": 12,
        "description": "Eco-friendly natural wool felt top with non-slip cork base and beveled edge detailing.",
    },
    {
        "id": 6,
        "name": "Ultra-Fast NVMe SSD Enclosure",
        "category": "Electronics",
        "price": 54.99,
        "stock": 18,
        "description": "Tool-free aluminum thermal enclosure supporting up to 10Gbps USB 3.2 Gen 2 transfer speeds.",
    },
]


def setup_default_browser_routes(page: Page) -> None:
    """Intercept backend API routes with deterministic responses for mocked UI testing."""
    page.route(
        "**/api/v1/auth/login",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "token": "fast-track-login-token",
                        "user": {
                            "id": 101,
                            "name": "Customer User",
                            "email": "customer@example.com",
                            "role": "customer",
                        },
                    }
                ),
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    page.route(
        "**/api/v1/auth/register",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "token": "fast-track-register-token",
                        "user": {
                            "id": 102,
                            "name": "Registered Customer",
                            "email": "customer@example.com",
                            "role": "customer",
                        },
                    }
                ),
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    page.route(
        "**/api/v1/orders/checkout",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": 901,
                        "order_id": "ORD-771122",
                        "user_id": 42,
                        "status": "confirmed",
                        "total_amount": 161.99,
                        "items_count": 1,
                    }
                ),
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    page.route(
        "**/health",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"status": "healthy", "database": "healthy"}),
            )
            if route.request.method == "GET"
            else route.continue_()
        ),
    )
    page.route(
        "**/api/v1/products",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "data": MOCK_PRODUCTS,
                        "products": MOCK_PRODUCTS,
                        "total": len(MOCK_PRODUCTS),
                        "page": 1,
                        "limit": 10,
                    }
                ),
            )
            if route.request.method == "GET"
            else (
                route.fulfill(
                    status=201,
                    content_type="application/json",
                    body=json.dumps({"id": 99, **(route.request.post_data_json or {})}),
                )
                if route.request.method == "POST"
                else route.continue_()
            )
        ),
    )
    page.route(
        "**/api/v1/products/*",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"deleted": True}),
            )
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )
    page.route(
        "**/api/v1/cart",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"items": [], "total_items": 0, "subtotal": 0.0}),
            )
            if route.request.method in ("GET", "DELETE")
            else route.continue_()
        ),
    )
    page.route(
        "**/api/v1/cart/items*",
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"items": [], "total_items": 0, "subtotal": 0.0}),
            )
            if route.request.method in ("POST", "PUT", "DELETE")
            else route.continue_()
        ),
    )
