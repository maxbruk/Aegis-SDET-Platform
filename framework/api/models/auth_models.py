"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Payload for POST /api/v1/auth/register."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserLoginRequest(BaseModel):
    """Payload for POST /api/v1/auth/login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserDTO(BaseModel):
    """User entity transfer object."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str | None = None
    email: str
    role: str = "customer"
    created_at: str | None = None


class AuthResponse(BaseModel):
    """Response returned upon successful login or registration."""

    model_config = ConfigDict(extra="ignore")

    token: str
    user: UserDTO
