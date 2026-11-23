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

from framework.api.auth_api import AuthAPI
from framework.api.models.auth_models import (
    AuthResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from framework.data.manager import TestDataManager
from framework.utils.data_factory import DataFactory


@allure.epic("API Contracts & Validation")
@allure.feature("Authentication Schemas & Lifecycle")
@pytest.mark.unit
@pytest.mark.api
class TestAuthAPIContract:
    """Contract tests for User and Authentication Pydantic v2 models."""

    @allure.story("User Registration Schema Validation")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_user_register_request_schema_validation(self):
        """Verifies valid UserRegisterRequest payload initializes correctly."""
        with allure.step("Instantiate valid UserRegisterRequest schema"):
            payload = {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "password": "SecurePassword123!",
            }
            model = UserRegisterRequest(**payload)
            assert model.name == "Jane Doe"
            assert model.email == "jane@example.com"

    @allure.story("Invalid Email Validation")
    @allure.severity(allure.severity_level.NORMAL)
    def test_user_register_request_rejects_invalid_email(self):
        """Ensures invalid email strings fail Pydantic model validation."""
        with (
            allure.step("Assert ValidationError on malformed email"),
            pytest.raises(ValidationError),
        ):
            UserRegisterRequest(
                name="Invalid",
                email="not-an-email",
                password="Password123!",
            )

    @allure.story("Short Password Validation")
    @allure.severity(allure.severity_level.NORMAL)
    def test_user_register_request_rejects_short_password(self):
        """Ensures passwords under 8 characters fail schema validation."""
        with (
            allure.step("Assert ValidationError on password < 8 chars"),
            pytest.raises(ValidationError),
        ):
            UserRegisterRequest(
                name="Short Pass",
                email="user@example.com",
                password="123",
            )

    @allure.story("Auth Response Deserialization")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_auth_response_deserialization(self):
        """Verifies AuthResponse schema deserializes JWT and User DTO."""
        with allure.step("Deserialize raw JWT response payload"):
            raw_response = {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
                "user": {
                    "id": 10,
                    "name": "Alex Taylor",
                    "email": "alex@example.com",
                    "role": "customer",
                    "created_at": "2026-08-30T12:00:00Z",
                },
            }
            auth_resp = AuthResponse.model_validate(raw_response)
            assert auth_resp.token.startswith("eyJ")
            assert auth_resp.user.id == 10
            assert auth_resp.user.role == "customer"


@allure.epic("API Contracts & Validation")
@allure.feature("Live Authentication Integration")
@pytest.mark.integration
@pytest.mark.api
class TestAuthAPIIntegration:
    """Integration tests executing HTTP calls against the backend."""

    @allure.story("Full Register -> Login -> Profile Flow")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_user_registration_and_login_flow(
        self,
        auth_api: AuthAPI,
        data_factory: DataFactory,
        test_data_manager: TestDataManager,
        backend_health: dict[str, str],
    ):
        """Tests registration -> login -> profile verification lifecycle."""
        del backend_health
        user_data = data_factory.random_user()

        with allure.step("Execute POST /api/v1/auth/register"):
            register_res = auth_api.register(UserRegisterRequest(**user_data))
            assert register_res.status_code in [200, 201], register_res.text
            reg_auth = AuthResponse.model_validate(register_res.json())
            test_data_manager.register_user_for_cleanup(reg_auth.user.id, reg_auth.token)

        with allure.step("Execute POST /api/v1/auth/login"):
            login_payload = UserLoginRequest(
                email=user_data["email"], password=user_data["password"]
            )
            login_res = auth_api.login(login_payload)
            assert login_res.status_code == 200
            data = login_res.json()
            assert "token" in data

        with allure.step("Execute GET /api/v1/auth/me"):
            me_res = auth_api.get_me()
            assert me_res.status_code == 200
            me_data = me_res.json()
            assert me_data["email"] == user_data["email"]
