"""Run context and per-run directory layout management."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from framework.config.settings import settings


class RunContext:
    """Manages unique run identifiers and isolated output directories for a test execution."""

    def __init__(
        self,
        run_id: str | None = None,
        runs_root: str | Path | None = None,
    ) -> None:
        self.run_id = run_id or self.resolve_run_id()
        self.runs_root = Path(runs_root or settings.RUNS_DIR)
        self.run_dir = self.runs_root / self.run_id

    @staticmethod
    def generate_run_id() -> str:
        """Generate a unique timestamped run identifier."""
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        suffix = uuid.uuid4().hex[:6]
        return f"run-{stamp}-{suffix}"

    @classmethod
    def resolve_run_id(cls) -> str:
        """Resolve run ID from environment, settings, or generate a new one."""
        env_id = os.environ.get("AEGIS_RUN_ID")
        if env_id:
            return env_id
        if settings.TEST_RUN_ID and settings.TEST_RUN_ID != "local":
            return settings.TEST_RUN_ID
        generated = cls.generate_run_id()
        os.environ["AEGIS_RUN_ID"] = generated
        return generated

    @property
    def screenshots_dir(self) -> Path:
        return self.run_dir / "screenshots"

    @property
    def traces_dir(self) -> Path:
        return self.run_dir / "traces"

    @property
    def videos_dir(self) -> Path:
        return self.run_dir / "videos"

    @property
    def network_dir(self) -> Path:
        return self.run_dir / "network"

    @property
    def logs_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def ai_diagnostics_dir(self) -> Path:
        return self.run_dir / "ai_diagnostics"

    @property
    def allure_results_dir(self) -> Path:
        return self.run_dir / "allure-results"

    @property
    def metadata_path(self) -> Path:
        return self.run_dir / "metadata.json"

    def ensure_directories(self) -> Path:
        """Create all per-run artifact subdirectories and return the run root path."""
        for directory in (
            self.run_dir,
            self.screenshots_dir,
            self.traces_dir,
            self.videos_dir,
            self.network_dir,
            self.logs_dir,
            self.ai_diagnostics_dir,
            self.allure_results_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self.run_dir
