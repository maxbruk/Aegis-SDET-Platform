"""TestDataManager with run/worker isolation and guaranteed teardown cleanup."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass

import httpx

from framework.api.auth_api import AuthAPI
from framework.api.cart_api import CartAPI
from framework.api.client import APIClientError, BaseAPIClient
from framework.api.models.auth_models import UserLoginRequest, UserRegisterRequest
from framework.api.models.cart_models import AddToCartRequest
from framework.api.models.order_models import CheckoutRequest
from framework.api.models.product_models import ProductCreateRequest
from framework.api.orders_api import OrdersAPI
from framework.api.products_api import ProductsAPI
from framework.config.settings import settings
from framework.execution.run_context import RunContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProvisionedUser:
    """Isolated customer entity provisioned for a single test execution."""

    user_id: int
    name: str
    email: str
    password: str
    token: str
    role: str = "customer"


@dataclass(frozen=True, slots=True)
class ProvisionedProduct:
    """Isolated product entity provisioned in PostgreSQL and tracked for cleanup."""

    product_id: int
    name: str
    price: float
    stock: int
    category: str


@dataclass(frozen=True, slots=True)
class ProvisionedOrder:
    """Isolated order entity created for downstream validation tests."""

    order_id: str
    idempotency_key: str
    total_amount: float
    user: ProvisionedUser
    product: ProvisionedProduct
    order_db_id: int = 0


class TestDataManager:
    """Provisions isolated test entities scoped by Run ID + worker ID and cleans up on teardown."""

    __test__ = False

    def __init__(
        self,
        api_url: str | None = None,
        run_context: RunContext | None = None,
    ) -> None:
        self.api_url = (api_url or settings.API_URL).rstrip("/")
        self.run_context = run_context or RunContext()
        self.worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
        self._created_product_ids: list[int] = []
        self._created_order_ids: list[int] = []
        self._created_user_ids: list[int] = []
        self._cart_tokens: list[str] = []
        self._created_user_emails: list[str] = []
        self._admin_token: str | None = None

    def unique_tag(self, prefix: str = "aegis") -> str:
        """Generate a unique tag scoped to run ID and xdist worker ID."""
        short_run = self.run_context.run_id[-6:]
        return f"{prefix}-{short_run}-{self.worker_id}-{uuid.uuid4().hex[:6]}"

    def get_admin_token(self) -> str:
        """Authenticate once as admin and cache the Bearer token for setup/teardown."""
        if self._admin_token is not None:
            return self._admin_token
        client = BaseAPIClient(base_url=self.api_url)
        try:
            auth = AuthAPI(client)
            res = auth.login(
                UserLoginRequest(email=settings.ADMIN_EMAIL, password=settings.ADMIN_PASSWORD)
            )
            if res.status_code != 200:
                raise RuntimeError(f"Admin authentication failed during setup: {res.text}")
            self._admin_token = str(res.json()["token"])
            return self._admin_token
        finally:
            client.close()

    def register_user_for_cleanup(self, user_id: int, token: str | None = None) -> None:
        """Track an externally registered user ID (and optional token) for teardown cleanup."""
        if user_id > 0 and user_id not in self._created_user_ids:
            self._created_user_ids.append(user_id)
        if token:
            self._cart_tokens.append(token)

    def register_order_for_cleanup(self, order_db_id: int) -> None:
        """Track an externally created order DB ID for teardown deletion."""
        if order_db_id > 0 and order_db_id not in self._created_order_ids:
            self._created_order_ids.append(order_db_id)

    def create_isolated_user(
        self,
        prefix: str = "user",
        password: str = "SecurePass!123",
    ) -> ProvisionedUser:
        """Register a fresh isolated customer account via the Go backend."""
        tag = self.unique_tag(prefix)
        email = f"{tag}@aegis-test.example.com"
        name = f"User {tag}"
        client = BaseAPIClient(base_url=self.api_url)
        try:
            auth = AuthAPI(client)
            res = auth.register(UserRegisterRequest(name=name, email=email, password=password))
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Failed to register isolated user: {res.text}")
            payload = res.json()
            token = str(payload["token"])
            user_dto = payload["user"]
            user_id = int(user_dto["id"])
            self._created_user_ids.append(user_id)
            self._created_user_emails.append(email)
            self._cart_tokens.append(token)
            return ProvisionedUser(
                user_id=user_id,
                name=str(user_dto.get("name", name)),
                email=str(user_dto["email"]),
                password=password,
                token=token,
                role=str(user_dto.get("role", "customer")),
            )
        finally:
            client.close()

    def create_isolated_product(
        self,
        price: float = 49.99,
        stock: int = 20,
        category: str = "Electronics",
        name: str | None = None,
    ) -> ProvisionedProduct:
        """Create an isolated catalog product as Admin and register it for cleanup."""
        prod_name = name or f"AEGIS Item {self.unique_tag('prod')}"
        admin_token = self.get_admin_token()
        client = BaseAPIClient(base_url=self.api_url)
        client.set_token(admin_token)
        try:
            products_api = ProductsAPI(client)
            res = products_api.create_product(
                ProductCreateRequest(
                    name=prod_name,
                    description=f"Isolated test item ({self.run_context.run_id})",
                    price=price,
                    stock=stock,
                    category=category,
                )
            )
            if res.status_code != 201:
                raise RuntimeError(f"Failed to create isolated product: {res.text}")
            data = res.json()
            product_id = int(data["id"])
            self._created_product_ids.append(product_id)
            return ProvisionedProduct(
                product_id=product_id,
                name=str(data["name"]),
                price=float(data["price"]),
                stock=int(data["stock"]),
                category=str(data["category"]),
            )
        finally:
            client.close()

    def provision_cart(self, user: ProvisionedUser, product_id: int, quantity: int = 1) -> None:
        """Seed a cart item for a provisioned customer."""
        client = BaseAPIClient(base_url=self.api_url)
        client.set_token(user.token)
        try:
            res = CartAPI(client).add_item(
                AddToCartRequest(product_id=product_id, quantity=quantity)
            )
            if res.status_code != 200:
                raise RuntimeError(f"Failed to provision cart: {res.text}")
        finally:
            client.close()

    def create_isolated_order(
        self,
        quantity: int = 1,
        price: float = 29.99,
        stock: int = 10,
        shipping_address: str = "1 Infinite Loop, Cupertino, CA",
    ) -> ProvisionedOrder:
        """Provision a user, product, and cart, then complete a checkout order."""
        user = self.create_isolated_user("buyer")
        product = self.create_isolated_product(price=price, stock=stock)
        self.provision_cart(user=user, product_id=product.product_id, quantity=quantity)
        idem_key = f"idem-{self.unique_tag('order')}"
        client = BaseAPIClient(base_url=self.api_url)
        client.set_token(user.token)
        try:
            res = OrdersAPI(client).checkout(
                CheckoutRequest(shipping_address=shipping_address),
                idempotency_key=idem_key,
            )
            if res.status_code != 200:
                raise RuntimeError(f"Failed to create isolated order: {res.text}")
            data = res.json()
            db_id = int(data.get("id", 0))
            if db_id > 0:
                self._created_order_ids.append(db_id)
            return ProvisionedOrder(
                order_id=str(data["order_id"]),
                idempotency_key=idem_key,
                total_amount=float(data["total_amount"]),
                user=user,
                product=product,
                order_db_id=db_id,
            )
        finally:
            client.close()

    def cleanup(self) -> None:
        """Delete all tracked orders, products, carts, and isolated users safely."""
        for token in self._cart_tokens:
            client = BaseAPIClient(base_url=self.api_url)
            client.set_token(token)
            try:
                CartAPI(client).clear_cart()
            except (httpx.HTTPError, APIClientError, RuntimeError, ValueError) as exc:
                logger.debug("Ignoring cart cleanup error: %s", exc)
            finally:
                client.close()
        self._cart_tokens.clear()

        if self._created_order_ids or self._created_product_ids or self._created_user_ids:
            try:
                admin_token = self.get_admin_token()
            except (APIClientError, RuntimeError) as exc:
                logger.debug("Skipping admin cleanup because admin login failed: %s", exc)
                admin_token = None
            if admin_token is not None:
                client = BaseAPIClient(base_url=self.api_url)
                client.set_token(admin_token)
                try:
                    orders_api = OrdersAPI(client)
                    for order_db_id in reversed(self._created_order_ids):
                        try:
                            orders_api.delete_order(order_db_id)
                        except (httpx.HTTPError, APIClientError) as exc:
                            logger.debug("Ignoring order cleanup error: %s", exc)

                    products_api = ProductsAPI(client)
                    for product_id in reversed(self._created_product_ids):
                        try:
                            products_api.delete_product(product_id)
                        except (httpx.HTTPError, APIClientError) as exc:
                            logger.debug("Ignoring product cleanup error: %s", exc)

                    auth_api = AuthAPI(client)
                    for user_id in reversed(self._created_user_ids):
                        try:
                            auth_api.delete_user(user_id)
                        except (httpx.HTTPError, APIClientError) as exc:
                            logger.debug("Ignoring user cleanup error: %s", exc)
                finally:
                    client.close()
            self._created_order_ids.clear()
            self._created_product_ids.clear()
            self._created_user_ids.clear()
            self._created_user_emails.clear()
