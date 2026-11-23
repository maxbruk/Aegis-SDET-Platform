"""Unit tests for core AEGIS framework utilities, config, and worker isolation."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from PIL import Image

from framework.api.client import APIConnectionError, APITimeoutError, BaseAPIClient
from framework.api.models.auth_models import UserRegisterRequest
from framework.config.settings import Settings
from framework.quality.visual import VisualDiffer
from framework.utils.data_factory import DataFactory
from tests.support.artifact_helpers import sanitize_node_id
from tests.support.test_data import WorkerTestData


@pytest.mark.unit
class TestFrameworkCore:
    """Deterministic unit tests with zero external network or browser dependencies."""

    def test_data_factory_generates_valid_unique_users(self) -> None:
        user_a = DataFactory.random_user()
        user_b = DataFactory.random_user()

        assert user_a["email"] != user_b["email"]
        model = UserRegisterRequest(**user_a)
        assert model.email == user_a["email"]
        assert len(model.password) >= 8

    def test_worker_test_data_namespaces_emails_and_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
        email = WorkerTestData.unique_email("buyer")
        idem = WorkerTestData.unique_idempotency_key()

        assert email.startswith("buyer.gw3-")
        assert idem.startswith("idem-gw3-")

    def test_sanitize_node_id_removes_unsafe_path_characters(self) -> None:
        raw = "tests/ui/test_storefront.py::TestStorefront::test_search[chromium]"
        sanitized = sanitize_node_id(raw)

        assert "/" not in sanitized
        assert ":" not in sanitized
        assert "[" not in sanitized
        assert "]" not in sanitized

    def test_settings_respects_environment_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_URL", "http://backend:3000")
        monkeypatch.setenv("REQUIRE_BACKEND", "true")
        cfg = Settings()

        assert cfg.API_URL == "http://backend:3000"
        assert cfg.REQUIRE_BACKEND is True

    def test_visual_differ_detects_identical_and_changed_images(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline.png"
        identical = tmp_path / "identical.png"
        modified = tmp_path / "modified.png"
        diff_out = tmp_path / "diff.png"

        Image.new("RGB", (100, 100), color=(255, 255, 255)).save(baseline)
        Image.new("RGB", (100, 100), color=(255, 255, 255)).save(identical)
        Image.new("RGB", (100, 100), color=(0, 0, 0)).save(modified)

        passed_same, pct_same = VisualDiffer.compare_images(
            actual_path=str(identical),
            baseline_path=str(baseline),
            diff_output_path=str(diff_out),
            mismatch_threshold_percent=1.0,
        )
        assert passed_same is True
        assert pct_same == 0.0

        passed_diff, pct_diff = VisualDiffer.compare_images(
            actual_path=str(modified),
            baseline_path=str(baseline),
            diff_output_path=str(diff_out),
            mismatch_threshold_percent=1.0,
        )
        assert passed_diff is False
        assert pct_diff == 100.0
        assert diff_out.exists()

    def test_api_client_raises_typed_transport_and_timeout_errors(self) -> None:
        client = BaseAPIClient("http://127.0.0.1:59999")
        try:
            with (
                patch.object(client._client, "request", side_effect=httpx.ConnectError("refused")),
                pytest.raises(APIConnectionError),
            ):
                client.get("/health")

            with (
                patch.object(client._client, "request", side_effect=httpx.ReadTimeout("timed out")),
                pytest.raises(APITimeoutError),
            ):
                client.get("/health")
        finally:
            client.close()

    def test_logreport_records_setup_failure_as_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from framework.config.settings import settings as global_settings
        from framework.telemetry.reliability import ReliabilityAnalyzer
        from tests import conftest as root_conftest

        monkeypatch.setattr(global_settings, "RELIABILITY_DIR", str(tmp_path))
        monkeypatch.setattr(root_conftest, "_IS_CONTROLLER", True)
        root_conftest._RECORDED_NODES.clear()

        fake_report = SimpleNamespace(
            when="setup",
            skipped=False,
            failed=True,
            passed=False,
            nodeid="tests/integration/test_demo.py::test_fixture_boom",
            duration=0.125,
            user_properties=[
                ("aegis_worker", "gw0"),
                ("aegis_failure_category", "infrastructure_failure"),
            ],
        )
        root_conftest.pytest_runtest_logreport(fake_report)  # type: ignore[arg-type]

        records = ReliabilityAnalyzer(
            history_path=tmp_path / "execution_history.jsonl"
        ).load_records()
        assert len(records) == 1
        assert records[0].status == "error"
        assert records[0].failure_category == "infrastructure_failure"
        root_conftest._RECORDED_NODES.clear()

    def test_logreport_teardown_failure_after_pass_upgrades_to_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from framework.config.settings import settings as global_settings
        from framework.telemetry.reliability import ReliabilityAnalyzer
        from tests import conftest as root_conftest

        monkeypatch.setattr(global_settings, "RELIABILITY_DIR", str(tmp_path))
        monkeypatch.setattr(root_conftest, "_IS_CONTROLLER", True)
        root_conftest._RECORDED_NODES.clear()

        nodeid = "tests/integration/test_demo.py::test_teardown_boom"
        root_conftest.pytest_runtest_logreport(
            SimpleNamespace(  # type: ignore[arg-type]
                when="call",
                skipped=False,
                failed=False,
                passed=True,
                nodeid=nodeid,
                duration=0.05,
                user_properties=[("aegis_worker", "gw0")],
            )
        )
        root_conftest.pytest_runtest_logreport(
            SimpleNamespace(  # type: ignore[arg-type]
                when="teardown",
                skipped=False,
                failed=True,
                passed=False,
                nodeid=nodeid,
                duration=0.02,
                user_properties=[
                    ("aegis_worker", "gw0"),
                    ("aegis_failure_category", "infrastructure_failure"),
                ],
            )
        )

        records = ReliabilityAnalyzer(
            history_path=tmp_path / "execution_history.jsonl"
        ).load_records()
        assert len(records) == 1
        assert records[0].status == "error"
        assert records[0].failure_category == "infrastructure_failure"
        root_conftest._RECORDED_NODES.clear()
