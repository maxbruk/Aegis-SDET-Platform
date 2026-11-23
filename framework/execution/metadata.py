"""Typed execution metadata model serialized per test run."""

from __future__ import annotations

import platform
from pathlib import Path

from pydantic import BaseModel, Field


class ExecutionMetadata(BaseModel):
    """Summary metadata describing an AEGIS test run."""

    run_id: str
    environment: str = "local"
    browser: str = "chromium"
    workers: int = Field(default=1, ge=1)
    python_version: str = Field(default_factory=platform.python_version)
    started_at: str
    finished_at: str | None = None
    duration_ms: float = Field(default=0.0, ge=0.0)
    total_tests: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)

    def save(self, path: str | Path) -> Path:
        """Persist metadata JSON to disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> ExecutionMetadata:
        """Load metadata JSON from disk."""
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
