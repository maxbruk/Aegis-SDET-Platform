"""Authentication API Client."""

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
from framework.api.models.auth_models import (
    UserLoginRequest,
    UserRegisterRequest,
)


class AuthAPI:
    """Encapsulates /api/v1/auth endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client

    def register(self, request_data: UserRegisterRequest | dict[str, Any]) -> APIResponse:
        """Register a new user account."""
        payload = (
            request_data.model_dump()
            if isinstance(request_data, UserRegisterRequest)
            else request_data
        )
        return self.client.post("/api/v1/auth/register", json_data=payload)

    def login(self, request_data: UserLoginRequest | dict[str, Any]) -> APIResponse:
        """Log in an existing user and return JWT token."""
        payload = (
            request_data.model_dump()
            if isinstance(request_data, UserLoginRequest)
            else request_data
        )
        response = self.client.post("/api/v1/auth/login", json_data=payload)
        if response.is_success:
            data = response.json()
            if "token" in data:
                self.client.set_token(data["token"])
        return response

    def get_me(self) -> APIResponse:
        """Get the authenticated user's profile."""
        return self.client.get("/api/v1/auth/me")
