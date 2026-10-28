"""Shopping cart: what a customer intends to buy before checkout."""

from __future__ import annotations

from typing import Optional


class Cart:
    """A single customer's cart, mapping SKU -> quantity.

    Rules:
      * Every customer has their own cart; carts never share contents.
      * Adding a SKU that's already in the cart increases that line's quantity
        (it does not create a second line).
      * Quantities must be positive integers. Anything else raises ValueError.
    """

    def __init__(self, customer_id: str, items: dict[str, int] = {}):
        self.customer_id = customer_id
        self.items = items

    def add(self, sku: str, quantity: int = 1) -> None:
        """Add `quantity` units of `sku` to the cart."""
        if not isinstance(quantity, int):
            raise ValueError(f"Quantity must be an integer, got {quantity!r}")
        self.items[sku] = self.items.get(sku, 0) + quantity

    def remove(self, sku: str, quantity: Optional[int] = None) -> None:
        """Remove `quantity` units of `sku`, or the whole line if quantity is None.

        A line that drops to zero is removed entirely. Removing a SKU that isn't
        in the cart is a no-op (the UI may send duplicate "remove" clicks).
        """
        if sku not in self.items:
            return
        if quantity is None or quantity >= self.items[sku]:
            del self.items[sku]
        else:
            self.items[sku] -= quantity

    def total_units(self) -> int:
        return sum(self.items.values())

    def is_empty(self) -> bool:
        return not self.items

    def clear(self) -> None:
        self.items.clear()

    def __repr__(self) -> str:
        return f"Cart(customer_id={self.customer_id!r}, items={self.items!r})"
