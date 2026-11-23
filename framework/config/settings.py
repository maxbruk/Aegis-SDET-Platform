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
    ENVIRONMENT: str = "local"
    CAPTURE_SCREENSHOT_ON_FAILURE: bool = True
    CAPTURE_TRACE_ON_FAILURE: bool = True
    CAPTURE_VIDEO_ON_FAILURE: bool = False
    UPDATE_VISUAL_BASELINES: bool = False
    ARTIFACTS_DIR: str = "reports/artifacts"
    RUNS_DIR: str = "reports/runs"
    RELIABILITY_DIR: str = "reports/reliability"
    MAX_STORED_RUNS: int = 10
    REQUIRE_BACKEND: bool = False
    TEST_RUN_ID: str = "local"
    AI_ENABLED: bool = True


# Global singleton instance
settings = Settings()
