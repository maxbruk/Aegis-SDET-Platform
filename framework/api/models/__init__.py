"""Models package exporting all API Pydantic schemas."""

from framework.api.models.auth_models import (
    AuthResponse,
    UserDTO,
    UserLoginRequest,
    UserRegisterRequest,
)
from framework.api.models.cart_models import (
    AddToCartRequest,
    CartItemDTO,
    CartResponse,
    UpdateCartItemRequest,
)
from framework.api.models.error_models import ErrorResponse
from framework.api.models.order_models import (
    CheckoutRequest,
    OrderItemDTO,
    OrderResponse,
)
from framework.api.models.product_models import (
    ProductCreateRequest,
    ProductDTO,
    ProductListResponse,
    ProductUpdateRequest,
)

__all__ = [
    "AddToCartRequest",
    "AuthResponse",
    "CartItemDTO",
    "CartResponse",
    "CheckoutRequest",
    "ErrorResponse",
    "OrderItemDTO",
    "OrderResponse",
    "ProductCreateRequest",
    "ProductDTO",
    "ProductListResponse",
    "ProductUpdateRequest",
    "UpdateCartItemRequest",
    "UserDTO",
    "UserLoginRequest",
    "UserRegisterRequest",
]
