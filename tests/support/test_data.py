"""Worker-isolated test data helpers for parallel pytest-xdist execution."""

import os
import uuid


class WorkerTestData:
    """Generates unique, worker-namespaced entities to prevent cross-worker collisions."""

    @staticmethod
    def worker_id() -> str:
        return os.environ.get("PYTEST_XDIST_WORKER", "main")

    @classmethod
    def unique_suffix(cls) -> str:
        return f"{cls.worker_id()}-{uuid.uuid4().hex[:8]}"

    @classmethod
    def unique_email(cls, prefix: str = "user") -> str:
        return f"{prefix}.{cls.unique_suffix()}@aegis-test.example.com"

    @classmethod
    def unique_idempotency_key(cls, prefix: str = "idem") -> str:
        return f"{prefix}-{cls.worker_id()}-{uuid.uuid4()}"
