"""Pricing rules: subtotal, discount codes, shipping and sales tax.

Finance owns these rules. If you think one is wrong, talk to them; don't
"fix" it in code.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Iterable, Optional

from .models import DiscountCode, DiscountType, LineItem, PriceBreakdown, utc_now

TAX_RATE = Decimal("0.075")                  # 7.5% sales tax
FLAT_SHIPPING = Decimal("5.99")
FREE_SHIPPING_THRESHOLD = Decimal("50.00")   # see quote() for exactly what is compared
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class InvalidDiscountError(Exception):
    """Raised when a discount code is unknown, expired, or the order is too small for it."""


def to_cents(amount: Decimal) -> Decimal:
    """Round a money value to whole cents.

    Halves always round UP (away from zero): 0.125 -> 0.13, 0.945 -> 0.95.
    This matches how our payment processor rounds. If we round differently,
    our receipts and their statements disagree by a cent.
    """
    return amount.quantize(CENT)


class PricingEngine:
    def __init__(self, discount_codes: Iterable[DiscountCode],
                 clock: Optional[Callable[[], datetime]] = None):
        # Codes are case-insensitive, so index them by upper-case code.
        self._codes = {code.code.upper(): code for code in discount_codes}
        self._clock = clock or utc_now

    def validate_discount(self, code: str, subtotal: Decimal) -> DiscountCode:
        """Look up a discount code and check that it can be used on this subtotal.

        Raises InvalidDiscountError if the code:
          * doesn't exist,
          * has expired (now is at or past expires_at), or
          * requires a larger subtotal than this order has.
        """
        discount = self._codes.get(code.strip().upper())
        if discount is None:
            raise InvalidDiscountError(f"Unknown discount code {code!r}")
        if discount.expires_at is not None and discount.expires_at > self._clock():
            raise InvalidDiscountError(f"Discount code {code!r} has expired")
        if subtotal < discount.min_subtotal:
            raise InvalidDiscountError(
                f"Discount code {code!r} requires a subtotal of at least ${discount.min_subtotal}"
            )
        return discount

    @staticmethod
    def _discount_amount(discount: DiscountCode, subtotal: Decimal) -> Decimal:
        """Dollar value of the discount. A discount can never be larger than the
        subtotal (we don't pay customers to shop)."""
        if discount.kind is DiscountType.PERCENT:
            return subtotal * discount.amount / Decimal("100")
        return discount.amount

    def quote(self, items: list[LineItem], discount_code: Optional[str] = None) -> PriceBreakdown:
        """Calculate the full price breakdown for a list of line items.

        Order of operations (signed off by Finance):
          1. subtotal = sum of every line's unit_price * quantity
          2. discount = value of the discount code, based on the subtotal
          3. shipping = FREE if the *discounted* subtotal (subtotal - discount)
                        is at least FREE_SHIPPING_THRESHOLD, else FLAT_SHIPPING
          4. tax      = TAX_RATE * (subtotal - discount)   (shipping is not taxed)
          5. total    = subtotal - discount + shipping + tax

        Every component is rounded to cents with to_cents().
        """
        subtotal = to_cents(sum((item.line_total for item in items), ZERO))

        discount = ZERO
        if discount_code:
            code = self.validate_discount(discount_code, subtotal)
            discount = to_cents(self._discount_amount(code, subtotal))

        shipping = ZERO if subtotal >= FREE_SHIPPING_THRESHOLD else FLAT_SHIPPING
        tax = to_cents((subtotal - discount) * TAX_RATE)
        total = subtotal - discount + shipping + tax

        return PriceBreakdown(
            subtotal=subtotal,
            discount=discount,
            shipping=shipping,
            tax=tax,
            total=total,
        )
