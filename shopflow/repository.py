"""Order storage.

Production swaps this class for a Postgres-backed one with the same methods,
so keep the interface small and don't let callers reach into the internals.
"""

from __future__ import annotations

from typing import Optional

from .models import Order


class InMemoryOrderRepository:
    def __init__(self):
        self._orders: dict[str, Order] = {}
        # Secondary index: idempotency_key -> Order, so retries can be found quickly.
        self._by_idempotency_key: dict[str, Order] = {}
        self._next_number = 1

    def next_id(self) -> str:
        """Generate a new unique, human-friendly order ID like 'ORD-000042'."""
        order_id = f"ORD-{self._next_number:06d}"
        self._next_number += 1
        return order_id

    def save(self, order: Order) -> None:
        """Insert a new order or update an existing one."""
        self._orders[order.order_id] = order
        if order.idempotency_key:
            self._by_idempotency_key[order.order_id] = order

    def get(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def find_by_idempotency_key(self, key: str) -> Optional[Order]:
        return self._by_idempotency_key.get(key)

    def all(self) -> list[Order]:
        return list(self._orders.values())

    def list_for_customer(self, customer_id: str, page: int = 1, page_size: int = 20) -> list[Order]:
        """Return one page of a customer's orders, newest first.

        `page` is 1-indexed, like the mobile app's UI: page=1 is the newest
        `page_size` orders, page=2 the next `page_size`, and so on. A page past
        the end returns an empty list.
        """
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be >= 1")
        orders = sorted(
            (o for o in self._orders.values() if o.customer_id == customer_id),
            key=lambda o: (o.created_at, o.order_id),
            reverse=True,
        )
        start = page * page_size
        return orders[start:start + page_size]
