"""Real integration tests against the Go REST backend and PostgreSQL database."""

import allure
import pytest

from framework.api.auth_api import AuthAPI
from framework.api.cart_api import CartAPI
from framework.api.client import BaseAPIClient
from framework.api.models.auth_models import UserLoginRequest
from framework.api.models.cart_models import (
    AddToCartRequest,
    CartResponse,
    UpdateCartItemRequest,
)
from framework.api.models.error_models import ErrorResponse
from framework.api.models.order_models import CheckoutRequest, OrderResponse
from framework.api.models.product_models import ProductCreateRequest, ProductUpdateRequest
from framework.api.orders_api import OrdersAPI
from framework.api.products_api import ProductsAPI
from framework.config.settings import settings
from framework.data.manager import TestDataManager
from framework.utils.data_factory import DataFactory
from tests.support.test_data import WorkerTestData


@allure.epic("Backend Integration")
@allure.feature("Go API + PostgreSQL ACID & RBAC")
@pytest.mark.integration
class TestBackendIntegration:
    """Executes real HTTP transactions against the Go backend and PostgreSQL."""

    def test_health_and_database_ready(self, backend_health: dict[str, str]) -> None:
        assert backend_health["status"] == "healthy"
        assert backend_health["database"] == "healthy"

    def test_cart_crud_lifecycle(
        self,
        auth_api: AuthAPI,
        cart_api: CartAPI,
        test_data_manager: TestDataManager,
        backend_health: dict[str, str],
    ) -> None:
        del backend_health
        product = test_data_manager.create_isolated_product(price=19.99, stock=10)
        buyer = test_data_manager.create_isolated_user("cart")
        auth_api.client.set_token(buyer.token)

        add_res = cart_api.add_item(AddToCartRequest(product_id=product.product_id, quantity=2))
        assert add_res.status_code == 200, add_res.text
        parsed_add = CartResponse.model_validate(add_res.json())
        assert parsed_add.total_items == 2

        upd_res = cart_api.update_quantity(product.product_id, UpdateCartItemRequest(quantity=3))
        assert upd_res.status_code == 200, upd_res.text
        assert CartResponse.model_validate(upd_res.json()).total_items == 3

        rem_res = cart_api.remove_item(product.product_id)
        assert rem_res.status_code == 200, rem_res.text
        assert CartResponse.model_validate(rem_res.json()).items == []

        clear_res = cart_api.clear_cart()
        assert clear_res.status_code == 200, clear_res.text
        assert clear_res.json()["items"] == []

    def test_acid_checkout_and_idempotency_deduplication(
        self,
        backend_health: dict[str, str],
        test_data_manager: TestDataManager,
    ) -> None:
        """Verifies isolated inventory deduction and Idempotency-Key duplicate protection."""
        del backend_health
        product = test_data_manager.create_isolated_product(price=25.00, stock=10)
        buyer = test_data_manager.create_isolated_user("idem")
        test_data_manager.provision_cart(buyer, product.product_id, quantity=2)

        client = BaseAPIClient(base_url=settings.API_URL)
        client.set_token(buyer.token)
        admin_client = BaseAPIClient(base_url=settings.API_URL)
        try:
            orders_api = OrdersAPI(client)
            idem_key = WorkerTestData.unique_idempotency_key("acid")
            checkout_req = CheckoutRequest(shipping_address="742 Evergreen Terrace, Springfield")

            first_order = orders_api.checkout(checkout_req, idempotency_key=idem_key)
            assert first_order.status_code == 200, first_order.text
            first_data = OrderResponse.model_validate(first_order.json())
            assert first_data.order_id is not None and first_data.order_id.startswith("ORD-")
            assert first_data.total_amount == 54.0
            if first_data.id:
                test_data_manager.register_order_for_cleanup(first_data.id)

            second_order = orders_api.checkout(checkout_req, idempotency_key=idem_key)
            assert second_order.status_code == 200, second_order.text
            second_data = OrderResponse.model_validate(second_order.json())
            assert second_data.order_id == first_data.order_id
            assert second_data.total_amount == first_data.total_amount

            AuthAPI(admin_client).login(
                UserLoginRequest(email=settings.ADMIN_EMAIL, password=settings.ADMIN_PASSWORD)
            )
            stock_res = ProductsAPI(admin_client).get_product(product.product_id)
            assert stock_res.status_code == 200
            assert stock_res.json()["stock"] == 8
        finally:
            client.close()
            admin_client.close()

    def test_security_unauthenticated_checkout_and_cross_user_idempotency_blocked(
        self,
        backend_health: dict[str, str],
        test_data_manager: TestDataManager,
    ) -> None:
        """Ensure unauthenticated checkout returns 401 and cross-user key reuse returns 409."""
        del backend_health
        provisioned = test_data_manager.create_isolated_order(quantity=1, price=30.0, stock=5)
        second_user = test_data_manager.create_isolated_user("attacker")

        anon_client = BaseAPIClient(base_url=settings.API_URL)
        other_client = BaseAPIClient(base_url=settings.API_URL)
        other_client.set_token(second_user.token)
        try:
            unauth_res = OrdersAPI(anon_client).checkout(
                {
                    "shipping_address": "100 Unauth Street, Austin, TX",
                    "items": [{"product_id": provisioned.product.product_id, "quantity": 1}],
                },
                idempotency_key=WorkerTestData.unique_idempotency_key("anon"),
            )
            assert unauth_res.status_code == 401
            err_model = ErrorResponse.model_validate(unauth_res.json())
            assert err_model.code == "UNAUTHORIZED"

            cross_user_res = OrdersAPI(other_client).checkout(
                {
                    "shipping_address": "200 Cross Tenant Way, Austin, TX",
                    "items": [{"product_id": provisioned.product.product_id, "quantity": 1}],
                },
                idempotency_key=provisioned.idempotency_key,
            )
            assert cross_user_res.status_code == 409
            conflict_err = ErrorResponse.model_validate(cross_user_res.json())
            assert conflict_err.code == "IDEMPOTENCY_KEY_CONFLICT"
        finally:
            anon_client.close()
            other_client.close()

    def test_admin_rbac_enforcement_and_product_crud(
        self,
        auth_api: AuthAPI,
        products_api: ProductsAPI,
        data_factory: DataFactory,
        test_data_manager: TestDataManager,
        backend_health: dict[str, str],
    ) -> None:
        del backend_health
        customer = test_data_manager.create_isolated_user("rbac")
        auth_api.client.set_token(customer.token)

        prod_payload = ProductCreateRequest(**data_factory.random_product())
        forbidden_res = products_api.create_product(prod_payload)
        assert forbidden_res.status_code == 403
        assert ErrorResponse.model_validate(forbidden_res.json()).code == "FORBIDDEN"

        admin_login = auth_api.login(
            UserLoginRequest(email=settings.ADMIN_EMAIL, password=settings.ADMIN_PASSWORD)
        )
        assert admin_login.status_code == 200, admin_login.text

        created_id: int | None = None
        try:
            create_res = products_api.create_product(prod_payload)
            assert create_res.status_code == 201, create_res.text
            created_id = create_res.json()["id"]

            upd_res = products_api.update_product(
                created_id,
                ProductUpdateRequest(stock=42),
            )
            assert upd_res.status_code == 200
            assert upd_res.json()["stock"] == 42
        finally:
            if created_id is not None:
                del_res = products_api.delete_product(created_id)
                assert del_res.status_code == 200
                assert products_api.get_product(created_id).status_code == 404
