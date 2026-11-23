"""Browser console and failed network request collectors for Playwright pages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import ConsoleMessage, Page, Request, Response


@dataclass(slots=True)
class ConsoleLogEntry:
    """Single browser console or uncaught page error event."""

    timestamp: str
    level: str
    text: str
    location: str = ""


@dataclass(slots=True)
class FailedNetworkRequest:
    """Captured failed HTTP request or HTTP error response (>= 400)."""

    timestamp: str
    method: str
    url: str
    status: int | None
    error_text: str
    resource_type: str = ""


class BrowserConsoleCollector:
    """Collects console messages and uncaught page errors from a Playwright Page."""

    def __init__(self) -> None:
        self.entries: list[ConsoleLogEntry] = []
        self._attached_pages: set[int] = set()

    def attach(self, page: Page) -> None:
        """Attach console and pageerror listeners to a Playwright Page once."""
        page_id = id(page)
        if page_id in self._attached_pages:
            return
        self._attached_pages.add(page_id)
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)

    def _on_console(self, msg: ConsoleMessage) -> None:
        loc = msg.location
        loc_str = f"{loc.get('url', '')}:{loc.get('lineNumber', '')}".strip(":")
        self.entries.append(
            ConsoleLogEntry(
                timestamp=datetime.now(UTC).isoformat(),
                level=msg.type,
                text=msg.text,
                location=loc_str,
            )
        )

    def _on_page_error(self, error: Exception) -> None:
        self.entries.append(
            ConsoleLogEntry(
                timestamp=datetime.now(UTC).isoformat(),
                level="pageerror",
                text=str(error),
            )
        )

    def format_text(self) -> str:
        """Render collected console entries as readable plain text."""
        if not self.entries:
            return "No browser console or pageerror events recorded.\n"
        lines = []
        for entry in self.entries:
            loc_suffix = f" ({entry.location})" if entry.location else ""
            lines.append(f"[{entry.timestamp}] [{entry.level.upper()}] {entry.text}{loc_suffix}")
        return "\n".join(lines) + "\n"


class NetworkFailureCollector:
    """Collects network transport failures and HTTP 4xx/5xx responses from a Page."""

    def __init__(self) -> None:
        self.entries: list[FailedNetworkRequest] = []
        self._attached_pages: set[int] = set()

    def attach(self, page: Page) -> None:
        """Attach requestfailed and response listeners to a Playwright Page once."""
        page_id = id(page)
        if page_id in self._attached_pages:
            return
        self._attached_pages.add(page_id)
        page.on("requestfailed", self._on_request_failed)
        page.on("response", self._on_response)

    def _on_request_failed(self, request: Request) -> None:
        self.entries.append(
            FailedNetworkRequest(
                timestamp=datetime.now(UTC).isoformat(),
                method=request.method,
                url=request.url,
                status=None,
                error_text=request.failure or "request failed",
                resource_type=request.resource_type,
            )
        )

    def _on_response(self, response: Response) -> None:
        if response.status >= 400:
            self.entries.append(
                FailedNetworkRequest(
                    timestamp=datetime.now(UTC).isoformat(),
                    method=response.request.method,
                    url=response.url,
                    status=response.status,
                    error_text=response.status_text or f"HTTP {response.status}",
                    resource_type=response.request.resource_type,
                )
            )

    def to_json(self) -> str:
        """Serialize collected network failures as formatted JSON."""
        return json.dumps([asdict(item) for item in self.entries], indent=2)
