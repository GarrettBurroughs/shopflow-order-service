"""Payment gateway client.

In production this wraps HTTP calls to our card processor. Locally (and in
tests) we use this in-memory fake, which behaves the same way from the
caller's point of view.

NOTE: Our processor does NOT de-duplicate charges. If you call charge() twice,
the customer is charged twice. Preventing duplicate charges is the order
service's job.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


class PaymentDeclinedError(Exception):
    """The card was declined (insufficient funds, over limit, fraud check, ...)."""


@dataclass
class Charge:
    charge_id: str
    customer_id: str
    amount: Decimal
    refunded: bool = False


class PaymentGateway:
    """In-memory stand-in for the card processor.

    Declines any charge larger than the customer's credit limit.
    """

    def __init__(self, credit_limits: Optional[dict[str, Decimal]] = None,
                 default_limit: Decimal = Decimal("1000.00")):
        self._credit_limits = credit_limits or {}
        self._default_limit = default_limit
        self.charges: dict[str, Charge] = {}

    def charge(self, customer_id: str, amount: Decimal) -> str:
        """Charge the customer's card and return a charge ID."""
        if amount <= 0:
            raise ValueError(f"Charge amount must be positive, got {amount}")
        limit = self._credit_limits.get(customer_id, self._default_limit)
        if amount > limit:
            raise PaymentDeclinedError(f"Card declined for {customer_id}: ${amount} exceeds limit")

        charge_id = f"ch_{uuid.uuid4().hex[:12]}"
        self.charges[charge_id] = Charge(charge_id, customer_id, amount)
        logger.info("Charged %s $%s (%s)", customer_id, amount, charge_id)
        return charge_id

    def refund(self, charge_id: str) -> None:
        """Refund a charge in full. Refunding twice is an error."""
        charge = self.charges.get(charge_id)
        if charge is None:
            raise KeyError(f"Unknown charge {charge_id}")
        if charge.refunded:
            raise ValueError(f"Charge {charge_id} was already refunded")
        charge.refunded = True
        logger.info("Refunded %s", charge_id)

    def charges_for(self, customer_id: str) -> list[Charge]:
        return [c for c in self.charges.values() if c.customer_id == customer_id]
