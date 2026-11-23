"""Base HTTP Client wrapper for API testing."""

import time
from typing import Any

import httpx


class APIClientError(RuntimeError):
    """Base error raised when an HTTP API transport call fails."""


class APIConnectionError(APIClientError):
    """Raised when the target API cannot be reached or returns a transport error."""


class APITimeoutError(APIClientError):
    """Raised when an API request exceeds the configured timeout."""


class APIResponse:
    """Rich wrapper around HTTP responses with telemetry and schema helpers."""

    def __init__(self, response: httpx.Response, elapsed_ms: float):
        self.raw = response
        self.status_code = response.status_code
        self.headers = response.headers
        self.elapsed_ms = elapsed_ms
        self._json_cache = None

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        if self._json_cache is None:
            self._json_cache = self.raw.json()
        return self._json_cache

    @property
    def text(self) -> str:
        return self.raw.text


class BaseAPIClient:
    """Production-grade API Client with session persistence, auth headers, and metrics."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=True,
        )

    def set_token(self, token: str) -> None:
        """Sets the Bearer JWT token for subsequent requests."""
        self.token = token

    def clear_token(self) -> None:
        """Clears the current authentication token."""
        self.token = None

    def _get_headers(self, custom_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> APIResponse:
        """Executes an HTTP request and measures response latency."""
        url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        req_headers = self._get_headers(headers)

        start_time = time.perf_counter()
        try:
            response = self._client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=req_headers,
            )
        except httpx.TimeoutException as exc:
            raise APITimeoutError(f"Request timed out: {method} {self.base_url}{url}") from exc
        except httpx.HTTPError as exc:
            raise APIConnectionError(
                f"Transport error for {method} {self.base_url}{url}: {exc}"
            ) from exc

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return APIResponse(response, elapsed_ms)

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> APIResponse:
        return self.request("GET", endpoint, params=params, headers=headers)

    def post(
        self, endpoint: str, json_data: Any | None = None, headers: dict[str, str] | None = None
    ) -> APIResponse:
        return self.request("POST", endpoint, json_data=json_data, headers=headers)

    def put(
        self, endpoint: str, json_data: Any | None = None, headers: dict[str, str] | None = None
    ) -> APIResponse:
        return self.request("PUT", endpoint, json_data=json_data, headers=headers)

    def delete(self, endpoint: str, headers: dict[str, str] | None = None) -> APIResponse:
        return self.request("DELETE", endpoint, headers=headers)

    def close(self) -> None:
        self._client.close()
