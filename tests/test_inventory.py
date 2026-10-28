import unittest
from datetime import datetime, timezone

from shopflow.inventory import InsufficientStockError, InventoryService


class FakeClock:
    """A clock tests can move forward manually."""

    def __init__(self):
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.inventory = InventoryService(clock=self.clock)
        self.inventory.restock("MUG", 10)
        self.inventory.restock("POSTER", 2)

    def test_restock_adds_to_on_hand(self):
        self.inventory.restock("MUG", 5)
        self.assertEqual(self.inventory.on_hand("MUG"), 15)
        self.assertEqual(self.inventory.available("MUG"), 15)

    def test_reserve_reduces_available_but_not_on_hand(self):
        self.inventory.reserve({"MUG": 3})
        self.assertEqual(self.inventory.available("MUG"), 7)
        self.assertEqual(self.inventory.on_hand("MUG"), 10)

    def test_reserve_is_all_or_nothing(self):
        with self.assertRaises(InsufficientStockError):
            self.inventory.reserve({"MUG": 2, "POSTER": 99})
        self.assertEqual(self.inventory.available("MUG"), 10)
        self.assertEqual(self.inventory.available("POSTER"), 2)

    def test_can_reserve_the_last_units(self):
        self.inventory.reserve({"POSTER": 2})
        self.assertEqual(self.inventory.available("POSTER"), 0)

    def test_commit_removes_units_from_on_hand(self):
        reservation = self.inventory.reserve({"MUG": 4})
        self.inventory.commit(reservation)
        self.assertEqual(self.inventory.on_hand("MUG"), 6)
        self.assertEqual(self.inventory.available("MUG"), 6)

    def test_release_returns_units_and_is_idempotent(self):
        reservation = self.inventory.reserve({"MUG": 4})
        self.inventory.release(reservation)
        self.inventory.release(reservation)  # second call must be a no-op
        self.assertEqual(self.inventory.available("MUG"), 10)

    def test_expire_does_nothing_when_no_reservations_are_stale(self):
        self.inventory.reserve({"MUG": 1})
        self.assertEqual(self.inventory.expire_stale_reservations(), 0)
        self.assertEqual(self.inventory.available("MUG"), 9)


if __name__ == "__main__":
    unittest.main()
