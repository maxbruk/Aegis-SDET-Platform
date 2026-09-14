"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Standard JSON error format returned by the Go backend."""

    model_config = ConfigDict(extra="ignore")

    error: str
    code: str | None = None
    status: int | None = None
