"""Order orchestration: checkout, cancellation, fulfilment and reporting.

OrderService is the only thing the HTTP/API layer talks to. It coordinates the
inventory, pricing, payment and repository components.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from .cart import Cart
from .inventory import InventoryService
from .models import LineItem, Order, OrderStatus, Product, utc_now
from .payments import PaymentDeclinedError, PaymentGateway
from .pricing import PricingEngine
from .repository import InMemoryOrderRepository

logger = logging.getLogger(__name__)


class OrderError(Exception):
    """A request that can't be fulfilled (empty cart, unknown order, ...)."""


class InvalidTransitionError(OrderError):
    """An order was asked to move to a status it can't reach from its current one."""


# Allowed status changes. Anything not listed here must be rejected.
#
#   PENDING   -> PAID        payment captured
#   PENDING   -> CANCELLED   customer abandoned before paying
#   PAID      -> SHIPPED     warehouse handed it to the carrier
#   PAID      -> CANCELLED   cancelled before shipping (refund + restock)
#   SHIPPED   -> DELIVERED   carrier confirmed delivery
#
# Once an order has SHIPPED it can no longer be cancelled; the customer has
# to go through the returns process instead. DELIVERED and CANCELLED are final.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


class OrderService:
    def __init__(
        self,
        catalog: dict[str, Product],
        inventory: InventoryService,
        pricing: PricingEngine,
        payments: PaymentGateway,
        repository: InMemoryOrderRepository,
    ):
        self._catalog = catalog
        self._inventory = inventory
        self._pricing = pricing
        self._payments = payments
        self._repo = repository

    # ------------------------------------------------------------------ checkout

    def place_order(
        self,
        cart: Cart,
        discount_code: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Order:
        """Check out a cart and return the resulting PAID order.

        Steps:
          1. Idempotency: if we already processed a request with this
             idempotency_key, return that original order unchanged. Mobile
             clients retry on network timeouts, and a retry must never charge
             the customer a second time.
          2. Validate: the cart must be non-empty and every SKU must exist.
          3. Reserve stock for every line (all-or-nothing).
          4. Price the order (this also validates the discount code).
          5. Charge the customer.
          6. Commit the reservation, save the order as PAID, empty the cart.

        If ANY step after (3) fails, the reservation must be released before the
        error propagates. Otherwise those units stay held and nobody can buy them.
        """
        if idempotency_key:
            existing = self._repo.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                logger.info("Replaying %s for idempotency key %s", existing.order_id, idempotency_key)
                return existing

        if cart.is_empty():
            raise OrderError("Cannot place an order with an empty cart")
        unknown = [sku for sku in cart.items if sku not in self._catalog]
        if unknown:
            raise OrderError(f"Unknown SKU(s): {', '.join(unknown)}")

        line_items = [
            LineItem(sku=sku, quantity=qty, unit_price=self._catalog[sku].unit_price)
            for sku, qty in cart.items.items()
        ]

        reservation_id = self._inventory.reserve(dict(cart.items))

        pricing = self._pricing.quote(line_items, discount_code)

        try:
            charge_id = self._payments.charge(cart.customer_id, pricing.total)
        except PaymentDeclinedError:
            logger.warning("Payment declined for %s; releasing %s", cart.customer_id, reservation_id)
            self._inventory.release(reservation_id)
            raise

        self._inventory.commit(reservation_id)

        order = Order(
            order_id=self._repo.next_id(),
            customer_id=cart.customer_id,
            items=line_items,
            pricing=pricing,
            discount_code=discount_code.strip().upper() if discount_code else None,
            idempotency_key=idempotency_key,
            charge_id=charge_id,
        )
        self._transition(order, OrderStatus.PAID)
        cart.clear()
        logger.info("Placed order %s for %s: $%s", order.order_id, order.customer_id, pricing.total)
        return order

    # ---------------------------------------------------------------- lifecycle

    def cancel_order(self, order_id: str) -> Order:
        """Cancel an order. If it had been paid, refund the charge and put the items back in stock."""
        order = self._get_or_raise(order_id)
        was_paid = order.status is OrderStatus.PAID

        self._transition(order, OrderStatus.CANCELLED)

        if was_paid:
            self._payments.refund(order.charge_id)
            for item in order.items:
                self._inventory.restock(item.sku, item.quantity)
        return order

    def ship_order(self, order_id: str) -> Order:
        order = self._get_or_raise(order_id)
        self._transition(order, OrderStatus.SHIPPED)
        return order

    def mark_delivered(self, order_id: str) -> Order:
        order = self._get_or_raise(order_id)
        self._transition(order, OrderStatus.DELIVERED)
        return order

    # ------------------------------------------------------------------ queries

    def get_order(self, order_id: str) -> Order:
        return self._get_or_raise(order_id)

    def order_history(self, customer_id: str, page: int = 1, page_size: int = 20) -> list[Order]:
        """A customer's orders, newest first. `page` is 1-indexed."""
        return self._repo.list_for_customer(customer_id, page=page, page_size=page_size)

    def total_revenue(self) -> Decimal:
        """Sum of `total` across every order that actually earned us money.

        Cancelled orders were refunded, so they must NOT be counted. This number
        feeds the Finance dashboard.
        """
        revenue = Decimal("0.00")
        for order in self._repo.all():
            if order.status != "cancelled":
                revenue += order.pricing.total
        return revenue

    # ------------------------------------------------------------------ helpers

    def _get_or_raise(self, order_id: str) -> Order:
        order = self._repo.get(order_id)
        if order is None:
            raise OrderError(f"Order {order_id} not found")
        return order

    def _transition(self, order: Order, new_status: OrderStatus) -> None:
        """Move an order to `new_status` if ALLOWED_TRANSITIONS permits it, then persist it."""
        if new_status not in ALLOWED_TRANSITIONS[order.status]:
            raise InvalidTransitionError(
                f"Order {order.order_id} cannot go from {order.status.value} to {new_status.value}"
            )
        logger.info("Order %s: %s -> %s", order.order_id, order.status.value, new_status.value)
        order.status = new_status
        order.updated_at = utc_now()
        self._repo.save(order)
