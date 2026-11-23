"""Backend concurrency, idempotency, race-condition, and transaction rollback tests."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import allure
import pytest

from framework.api.client import BaseAPIClient
from framework.api.models.order_models import CheckoutRequest
from framework.api.orders_api import OrdersAPI
from framework.api.products_api import ProductsAPI
from framework.config.settings import settings
from framework.data.manager import TestDataManager


@allure.epic("Backend Concurrency & ACID Guarantees")
@allure.feature("Idempotency, Inventory Race Conditions & Transaction Rollback")
@pytest.mark.concurrency
@pytest.mark.integration
class TestBackendConcurrency:
    """High-concurrency scenarios verifying PostgreSQL row locks and transaction atomicity."""

    def test_concurrent_idempotent_checkout_creates_single_order(
        self,
        backend_health: dict[str, str],
        test_data_manager: TestDataManager,
    ) -> None:
        """Scenario A: 10 parallel checkout calls with identical Idempotency-Key create 1 order."""
        del backend_health
        product = test_data_manager.create_isolated_product(price=20.0, stock=20)
        buyer = test_data_manager.create_isolated_user("idem-conc")
        idem_key = f"conc-idem-{test_data_manager.unique_tag()}"
        barrier = threading.Barrier(10)

        def submit_checkout() -> tuple[int, str]:
            client = BaseAPIClient(base_url=settings.API_URL)
            client.set_token(buyer.token)
            try:
                barrier.wait(timeout=10.0)
                res = OrdersAPI(client).checkout(
                    {
                        "shipping_address": "100 Concurrency Way, Austin, TX",
                        "payment_method": "credit_card",
                        "items": [{"product_id": product.product_id, "quantity": 3}],
                    },
                    idempotency_key=idem_key,
                )
                order_id = res.json().get("order_id", "") if res.is_success else ""
                return res.status_code, order_id
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: submit_checkout(), range(10)))

        statuses = [status for status, _ in results]
        order_ids = {oid for _, oid in results}
        assert all(code == 200 for code in statuses), f"Unexpected statuses: {statuses}"
        assert len(order_ids) == 1, f"Expected single deduplicated order_id, got: {order_ids}"

        admin_client = BaseAPIClient(base_url=settings.API_URL)
        admin_client.set_token(test_data_manager.get_admin_token())
        try:
            prod_res = ProductsAPI(admin_client).get_product(product.product_id)
            assert prod_res.status_code == 200
            assert prod_res.json()["stock"] == 17
        finally:
            admin_client.close()

    def test_inventory_race_condition_never_oversells_or_goes_negative(
        self,
        backend_health: dict[str, str],
        test_data_manager: TestDataManager,
    ) -> None:
        """Scenario B: 12 concurrent buyers compete for 5 units; max 5 succeed and stock == 0."""
        del backend_health
        initial_stock = 5
        buyers_count = 12
        product = test_data_manager.create_isolated_product(price=35.0, stock=initial_stock)
        buyers = [test_data_manager.create_isolated_user(f"racer-{i}") for i in range(buyers_count)]
        barrier = threading.Barrier(buyers_count)

        def buy_one(token: str) -> int:
            client = BaseAPIClient(base_url=settings.API_URL)
            client.set_token(token)
            try:
                barrier.wait(timeout=10.0)
                res = OrdersAPI(client).checkout(
                    {
                        "shipping_address": "200 Race Condition Blvd, Seattle, WA",
                        "payment_method": "credit_card",
                        "items": [{"product_id": product.product_id, "quantity": 1}],
                    },
                    idempotency_key=f"race-{test_data_manager.unique_tag()}",
                )
                return res.status_code
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=buyers_count) as pool:
            statuses = list(pool.map(buy_one, [b.token for b in buyers]))

        succeeded = sum(1 for code in statuses if code == 200)
        conflicts = sum(1 for code in statuses if code == 409)
        assert succeeded == initial_stock, f"Expected {initial_stock} successes, got {statuses}"
        assert conflicts == buyers_count - initial_stock, f"Unexpected rejections: {statuses}"

        admin_client = BaseAPIClient(base_url=settings.API_URL)
        admin_client.set_token(test_data_manager.get_admin_token())
        try:
            prod_res = ProductsAPI(admin_client).get_product(product.product_id)
            assert prod_res.status_code == 200
            assert prod_res.json()["stock"] == 0
        finally:
            admin_client.close()

    def test_checkout_transaction_rollback_leaves_inventory_unchanged(
        self,
        backend_health: dict[str, str],
        test_data_manager: TestDataManager,
    ) -> None:
        """Scenario C: Multi-item checkout failing on item B must roll back item A deduction."""
        del backend_health
        product_a = test_data_manager.create_isolated_product(price=15.0, stock=5)
        product_b = test_data_manager.create_isolated_product(price=25.0, stock=1)
        buyer = test_data_manager.create_isolated_user("rollback")

        client = BaseAPIClient(base_url=settings.API_URL)
        client.set_token(buyer.token)
        try:
            # Item A (qty=2 <= 5) succeeds lock, Item B (qty=3 > 1) fails -> whole tx rolls back
            res = OrdersAPI(client).checkout(
                {
                    "shipping_address": "300 Rollback Rd, Denver, CO",
                    "payment_method": "credit_card",
                    "items": [
                        {"product_id": product_a.product_id, "quantity": 2},
                        {"product_id": product_b.product_id, "quantity": 3},
                    ],
                },
                idempotency_key=f"rb-{test_data_manager.unique_tag()}",
            )
            assert res.status_code == 409, res.text

            orders_res = OrdersAPI(client).get_orders()
            assert orders_res.status_code == 200
            assert orders_res.json()["orders"] == []
        finally:
            client.close()

        admin_client = BaseAPIClient(base_url=settings.API_URL)
        admin_client.set_token(test_data_manager.get_admin_token())
        try:
            products_api = ProductsAPI(admin_client)
            assert products_api.get_product(product_a.product_id).json()["stock"] == 5
            assert products_api.get_product(product_b.product_id).json()["stock"] == 1
        finally:
            admin_client.close()

    def test_empty_cart_checkout_rejected_cleanly(
        self,
        backend_health: dict[str, str],
        test_data_manager: TestDataManager,
    ) -> None:
        del backend_health
        buyer = test_data_manager.create_isolated_user("empty-cart")
        client = BaseAPIClient(base_url=settings.API_URL)
        client.set_token(buyer.token)
        try:
            res = OrdersAPI(client).checkout(
                CheckoutRequest(shipping_address="400 Empty Cart Ave, Miami, FL")
            )
            assert res.status_code == 400
        finally:
            client.close()
