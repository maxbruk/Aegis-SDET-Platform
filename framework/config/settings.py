"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

"""Framework configuration and environment settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base URLs
    BASE_URL: str = "http://127.0.0.1:8080"
    API_URL: str = "http://127.0.0.1:3000"

    # Default Credentials
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "password123"
    CUSTOMER_EMAIL: str = "customer@example.com"
    CUSTOMER_PASSWORD: str = "password123"

    # Playwright Execution Controls
    HEADLESS: bool = True
    BROWSER_NAME: str = "chromium"
    DEFAULT_TIMEOUT_MS: int = 10000
    SLOW_MO_MS: int = 0
    VIEWPORT_WIDTH: int = 1280
    VIEWPORT_HEIGHT: int = 800

    # Test Infrastructure & Reporting
    CAPTURE_SCREENSHOT_ON_FAILURE: bool = True
    CAPTURE_TRACE_ON_FAILURE: bool = True
    ARTIFACTS_DIR: str = "reports/artifacts"


# Global singleton instance
settings = Settings()
