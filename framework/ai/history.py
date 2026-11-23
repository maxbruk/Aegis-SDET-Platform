"""Structured historical failure storage and similarity matching."""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from framework.config.settings import settings


class FailureHistoryEntry(BaseModel):
    """Normalized record of a past test failure."""

    run_id: str
    test_id: str
    category: str
    error_message: str
    normalized_signature: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class HistoricalMatch(BaseModel):
    """Similar past failure surfaced for triage context."""

    run_id: str
    test_id: str
    category: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    error_message: str
    timestamp: str


def redact_sensitive_text(raw: str) -> str:
    """Mask bearer tokens, JWTs, and password parameters before persisting diagnostics."""
    masked = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9\-_.~+/=]+",
        r"\1[REDACTED]",
        raw,
    )
    masked = re.sub(
        r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
        "[REDACTED_JWT]",
        masked,
    )
    masked = re.sub(
        r"(?i)(password[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)",
        r"\1[REDACTED]",
        masked,
    )
    return masked


def normalize_error_signature(error_message: str) -> str:
    """Strip ephemeral IDs, hex pointers, and numbers so similar errors cluster together."""
    text = redact_sensitive_text(error_message).lower()
    text = re.sub(r"0x[0-9a-f]+", "<hex>", text)
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}", "<uuid>", text)
    text = re.sub(r"\d+", "<num>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_jaccard(sig_a: str, sig_b: str) -> float:
    tokens_a = {t for t in re.split(r"[^a-z<>]+", sig_a) if len(t) >= 2}
    tokens_b = {t for t in re.split(r"[^a-z<>]+", sig_b) if len(t) >= 2}
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


@contextlib.contextmanager
def _file_lock(lock_path: Path, timeout_seconds: float = 2.0) -> Iterator[None]:
    """Acquire an exclusive advisory lock file for cross-worker JSONL writes."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    acquired = False
    while time.monotonic() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            with contextlib.suppress(OSError):
                if time.time() - lock_path.stat().st_mtime > 10.0:
                    lock_path.unlink(missing_ok=True)
                    continue
            time.sleep(0.02)
    try:
        yield
    finally:
        if acquired:
            lock_path.unlink(missing_ok=True)


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp_", suffix=".jsonl")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


class HistoricalFailureStore:
    """Appends failure signatures to JSONL history and retrieves similar past failures."""

    def __init__(
        self,
        history_path: str | Path | None = None,
        max_entries: int = 1000,
    ) -> None:
        base_dir = Path(settings.RELIABILITY_DIR)
        self.history_path = (
            Path(history_path) if history_path else base_dir / "failure_history.jsonl"
        )
        self.max_entries = max_entries

    def record_failure(
        self,
        run_id: str,
        test_id: str,
        category: str,
        error_message: str,
    ) -> FailureHistoryEntry:
        """Append a redacted, normalized failure record to history with cross-worker lock."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        sanitized_message = redact_sensitive_text(error_message[:1000])
        entry = FailureHistoryEntry(
            run_id=run_id,
            test_id=test_id,
            category=category,
            error_message=sanitized_message,
            normalized_signature=normalize_error_signature(sanitized_message),
        )
        lock_file = self.history_path.with_suffix(".lock")
        with _file_lock(lock_file):
            with self.history_path.open("a", encoding="utf-8") as fh:
                fh.write(entry.model_dump_json() + "\n")
            if self.max_entries > 0:
                lines = [
                    ln
                    for ln in self.history_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip()
                ]
                if len(lines) > self.max_entries:
                    _atomic_write_text(
                        self.history_path,
                        "\n".join(lines[-self.max_entries :]) + "\n",
                    )
        return entry

    def load_entries(self) -> list[FailureHistoryEntry]:
        if not self.history_path.exists():
            return []
        entries: list[FailureHistoryEntry] = []
        for raw in self.history_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                entries.append(FailureHistoryEntry.model_validate_json(line))
            except ValueError:
                continue
        return entries

    def find_similar(
        self,
        error_message: str,
        min_similarity: float = 0.35,
        limit: int = 5,
    ) -> list[HistoricalMatch]:
        """Return most similar past failures ordered by Jaccard similarity."""
        query_sig = normalize_error_signature(error_message)
        matches: list[HistoricalMatch] = []
        for entry in self.load_entries():
            score = _token_jaccard(query_sig, entry.normalized_signature)
            if score >= min_similarity:
                matches.append(
                    HistoricalMatch(
                        run_id=entry.run_id,
                        test_id=entry.test_id,
                        category=entry.category,
                        similarity_score=round(score, 3),
                        error_message=entry.error_message,
                        timestamp=entry.timestamp,
                    )
                )
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches[:limit]
