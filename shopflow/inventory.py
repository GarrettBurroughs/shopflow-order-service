"""Stock levels and checkout reservations."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from .models import utc_now

logger = logging.getLogger(__name__)


class InsufficientStockError(Exception):
    def __init__(self, sku: str, requested: int, available: int):
        super().__init__(f"Not enough stock for {sku}: requested {requested}, available {available}")
        self.sku = sku
        self.requested = requested
        self.available = available


@dataclass
class Reservation:
    reservation_id: str
    sku_quantities: dict[str, int]
    expires_at: datetime


class InventoryService:
    """Tracks on-hand stock and short-lived reservations ("holds").

    When checkout starts we *reserve* the units so two customers can't both buy
    the last one. Every reservation ends in exactly one of three ways:

      * commit()  - the order was paid; held units leave the warehouse for good.
      * release() - checkout failed or was abandoned; held units become
                    available to other shoppers again.
      * expiry    - nobody committed or released it within RESERVATION_TTL.
                    A background job calls expire_stale_reservations() every
                    minute, which releases these.

    Stock math:  available = on_hand - reserved
    """

    RESERVATION_TTL = timedelta(minutes=15)

    def __init__(self, clock: Optional[Callable[[], datetime]] = None):
        self._on_hand: dict[str, int] = {}
        self._reserved: dict[str, int] = {}
        self._reservations: dict[str, Reservation] = {}
        # Injected so tests can control time. Defaults to the real clock.
        self._clock = clock or utc_now

    def restock(self, sku: str, quantity: int) -> None:
        """Add units to on-hand stock (new shipment from a supplier, or a cancelled order)."""
        if quantity <= 0:
            raise ValueError("Restock quantity must be positive")
        self._on_hand[sku] = self._on_hand.get(sku, 0) + quantity

    def on_hand(self, sku: str) -> int:
        return self._on_hand.get(sku, 0)

    def available(self, sku: str) -> int:
        """Units a new customer could buy right now."""
        return self._on_hand.get(sku, 0) - self._reserved.get(sku, 0)

    def reserve(self, sku_quantities: dict[str, int]) -> str:
        """Hold stock for a checkout and return a reservation ID.

        All-or-nothing: if ANY sku doesn't have enough available stock, raise
        InsufficientStockError and reserve nothing at all. A customer may
        reserve every remaining unit (e.g. buy the last 2 of 2).
        """
        for sku, qty in sku_quantities.items():
            if self.available(sku) <= qty:
                raise InsufficientStockError(sku, requested=qty, available=self.available(sku))

        for sku, qty in sku_quantities.items():
            self._reserved[sku] = self._reserved.get(sku, 0) + qty

        reservation_id = f"res_{uuid.uuid4().hex[:12]}"
        self._reservations[reservation_id] = Reservation(
            reservation_id=reservation_id,
            sku_quantities=dict(sku_quantities),
            expires_at=self._clock() + self.RESERVATION_TTL,
        )
        logger.info("Created reservation %s: %s", reservation_id, sku_quantities)
        return reservation_id

    def commit(self, reservation_id: str) -> None:
        """Turn a reservation into a sale: held units are removed from on-hand stock."""
        reservation = self._reservations.pop(reservation_id, None)
        if reservation is None:
            raise KeyError(f"Unknown or already-finished reservation {reservation_id}")
        for sku, qty in reservation.sku_quantities.items():
            self._reserved[sku] -= qty
            self._on_hand[sku] -= qty
        logger.info("Committed reservation %s", reservation_id)

    def release(self, reservation_id: str) -> None:
        """Give held units back to available stock.

        Safe to call more than once: releasing an unknown or already-finished
        reservation does nothing.
        """
        reservation = self._reservations.pop(reservation_id, None)
        if reservation is None:
            return
        for sku, qty in reservation.sku_quantities.items():
            self._reserved[sku] -= qty
        logger.info("Released reservation %s", reservation_id)

    def active_reservations(self) -> int:
        return len(self._reservations)

    def expire_stale_reservations(self) -> int:
        """Release every reservation whose TTL has passed. Returns how many were released.

        Called by a background job once a minute.
        """
        now = self._clock()
        released = 0
        for reservation_id, reservation in self._reservations.items():
            if reservation.expires_at <= now:
                self.release(reservation_id)
                released += 1
        return released
