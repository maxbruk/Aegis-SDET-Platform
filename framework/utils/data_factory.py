"""
=========================================================
 Python SDET Enterprise Automation Platform & Storefront
 End-to-End Quality Engineering with Playwright & Pytest
 COM Architecture, Network Chaos, CDP Metrics & Allure

 Developed by Max Bruk, August 2026
=========================================================
"""

import random
import uuid
from typing import Any

from faker import Faker

fake = Faker()


class DataFactory:
    """Factory creating isolated test entities for API and UI test runs."""

    @staticmethod
    def random_user(role: str = "customer") -> dict[str, str]:
        """Generate random user registration data."""
        suffix = uuid.uuid4().hex[:6]
        return {
            "name": fake.name(),
            "email": f"test.user.{suffix}@{fake.domain_name()}",
            "password": f"Pass!{suffix}99#",
            "role": role,
        }

    @staticmethod
    def random_shipping_address() -> str:
        """Generate a realistic street address."""
        return f"{fake.street_address()}, {fake.city()}, {fake.state_abbr()} {fake.zipcode()}"

    @staticmethod
    def random_address() -> str:
        """Generate a realistic street address (alias)."""
        return DataFactory.random_shipping_address()

    @staticmethod
    def random_product() -> dict[str, Any]:
        """Generate a random new product payload for admin tests."""
        categories = ["Electronics", "Accessories", "Audio", "Workspace"]
        return {
            "name": f"{fake.word().capitalize()} {fake.word().capitalize()} Pro",
            "description": fake.sentence(nb_words=10),
            "price": round(random.uniform(19.99, 399.99), 2),
            "stock": random.randint(10, 100),
            "category": random.choice(categories),
        }

    @staticmethod
    def random_idempotency_key() -> str:
        """Generate a standard UUID v4 idempotency key."""
        return str(uuid.uuid4())
