"""Domain models for the ShopFlow order service.

These are plain data containers with no business logic. The services in this
package (inventory, pricing, order_service) operate on them.

All money values are `decimal.Decimal`, never `float`, so that cents add up
exactly. (0.1 + 0.2 != 0.3 with floats.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime. Use this instead of datetime.now()."""
    return datetime.now(timezone.utc)


class OrderStatus(Enum):
    """Lifecycle of an order. See ALLOWED_TRANSITIONS in order_service.py."""

    PENDING = "pending"      # created, payment not yet captured
    PAID = "paid"            # payment captured, waiting to ship
    SHIPPED = "shipped"      # handed to the carrier
    DELIVERED = "delivered"  # carrier confirmed delivery (final)
    CANCELLED = "cancelled"  # cancelled before shipping (final)


class DiscountType(Enum):
    PERCENT = "percent"  # `amount` is a percentage, e.g. Decimal("15") means 15% off
    FIXED = "fixed"      # `amount` is a dollar value, e.g. Decimal("10.00") means $10 off


@dataclass(frozen=True)
class Product:
    """An item in the catalog. `sku` (stock keeping unit) is the unique product ID."""

    sku: str
    name: str
    unit_price: Decimal


@dataclass(frozen=True)
class DiscountCode:
    code: str
    kind: DiscountType
    amount: Decimal
    # The order subtotal must be at least this much for the code to apply.
    min_subtotal: Decimal = Decimal("0.00")
    # None means the code never expires. Otherwise the code stops working at this moment.
    expires_at: Optional[datetime] = None


@dataclass
class LineItem:
    """One row on an order: a product, how many, and the unit price at time of purchase."""

    sku: str
    quantity: int
    unit_price: Decimal

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class PriceBreakdown:
    """Everything the customer sees on the receipt. See PricingEngine.quote()."""

    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: list[LineItem]
    pricing: PriceBreakdown
    status: OrderStatus = OrderStatus.PENDING
    discount_code: Optional[str] = None
    # Client-supplied key that makes checkout safe to retry. See OrderService.place_order().
    idempotency_key: Optional[str] = None
    # ID returned by the payment gateway; needed to issue refunds.
    charge_id: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
