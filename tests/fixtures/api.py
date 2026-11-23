"""API client fixtures and live backend healthcheck gate."""

from collections.abc import Generator

import pytest

from framework.api.auth_api import AuthAPI
from framework.api.cart_api import CartAPI
from framework.api.client import APIClientError, BaseAPIClient
from framework.api.orders_api import OrdersAPI
from framework.api.products_api import ProductsAPI
from framework.config.settings import settings


@pytest.fixture(scope="session")
def backend_health() -> dict[str, str]:
    """Verify that the Go backend and PostgreSQL database are healthy."""
    client = BaseAPIClient(base_url=settings.API_URL)
    try:
        res = client.get("/health")
    except APIClientError as exc:
        msg = f"Backend API at {settings.API_URL} is unavailable: {exc}"
        if settings.REQUIRE_BACKEND:
            pytest.fail(msg)
        pytest.skip(f"{msg} Set REQUIRE_BACKEND=true or run via Docker Compose to enforce.")
    finally:
        client.close()

    if not res.is_success:
        msg = f"Backend API at {settings.API_URL} is unavailable (status {res.status_code})."
        if settings.REQUIRE_BACKEND:
            pytest.fail(msg)
        pytest.skip(f"{msg} Set REQUIRE_BACKEND=true or run via Docker Compose to enforce.")

    payload = res.json()
    if payload.get("status") != "healthy" or payload.get("database") != "healthy":
        msg = f"Backend healthcheck degraded: {payload}"
        if settings.REQUIRE_BACKEND:
            pytest.fail(msg)
        pytest.skip(msg)
    return payload


@pytest.fixture(scope="function")
def api_client() -> Generator[BaseAPIClient, None, None]:
    """Provide an isolated per-test HTTP client so auth tokens never leak across tests."""
    client = BaseAPIClient(base_url=settings.API_URL)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="function")
def auth_api(api_client: BaseAPIClient) -> AuthAPI:
    return AuthAPI(api_client)


@pytest.fixture(scope="function")
def products_api(api_client: BaseAPIClient) -> ProductsAPI:
    return ProductsAPI(api_client)


@pytest.fixture(scope="function")
def cart_api(api_client: BaseAPIClient) -> CartAPI:
    return CartAPI(api_client)


@pytest.fixture(scope="function")
def orders_api(api_client: BaseAPIClient) -> OrdersAPI:
    return OrdersAPI(api_client)
