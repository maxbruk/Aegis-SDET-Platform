"""Unit tests for TestDataManager isolation and guaranteed teardown cleanup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from framework.data.manager import TestDataManager
from framework.execution.run_context import RunContext


@pytest.mark.unit
class TestDataManagerUnit:
    """Validates unique tagging and cleanup behavior of TestDataManager."""

    def test_unique_tag_includes_run_id_and_worker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw2")
        ctx = RunContext(run_id="run-20261116-abcdef", runs_root=tmp_path)
        manager = TestDataManager(api_url="http://127.0.0.1:3000", run_context=ctx)

        tag = manager.unique_tag("order")
        assert tag.startswith("order-abcdef-gw2-")

    def test_cleanup_removes_tracked_products_and_clears_carts(self, tmp_path: Path) -> None:
        ctx = RunContext(run_id="run-cleanup-123456", runs_root=tmp_path)
        manager = TestDataManager(api_url="http://127.0.0.1:3000", run_context=ctx)
        manager._admin_token = "admin-jwt"
        manager._created_product_ids.extend([101, 102])
        manager._cart_tokens.append("cust-jwt")

        with (
            patch("framework.data.manager.CartAPI") as mock_cart_cls,
            patch("framework.data.manager.ProductsAPI") as mock_prod_cls,
        ):
            mock_cart_cls.return_value = MagicMock()
            mock_prod_cls.return_value = MagicMock()

            manager.cleanup()

            mock_cart_cls.return_value.clear_cart.assert_called_once()
            delete_calls = [
                call.args[0] for call in mock_prod_cls.return_value.delete_product.call_args_list
            ]
            assert delete_calls == [102, 101]
            assert manager._created_product_ids == []
            assert manager._cart_tokens == []

    def test_register_order_and_user_for_cleanup(self, tmp_path: Path) -> None:
        ctx = RunContext(run_id="run-cleanup-654321", runs_root=tmp_path)
        manager = TestDataManager(api_url="http://127.0.0.1:3000", run_context=ctx)
        manager._admin_token = "admin-jwt"
        manager.register_order_for_cleanup(501)
        manager.register_user_for_cleanup(601, "user-jwt")

        with (
            patch("framework.data.manager.CartAPI") as mock_cart_cls,
            patch("framework.data.manager.OrdersAPI") as mock_orders_cls,
            patch("framework.data.manager.AuthAPI") as mock_auth_cls,
        ):
            mock_cart_cls.return_value = MagicMock()
            mock_orders_cls.return_value = MagicMock()
            mock_auth_cls.return_value = MagicMock()

            manager.cleanup()

            mock_cart_cls.return_value.clear_cart.assert_called_once()
            mock_orders_cls.return_value.delete_order.assert_called_once_with(501)
            mock_auth_cls.return_value.delete_user.assert_called_once_with(601)
