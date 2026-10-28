import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from shopflow.models import DiscountCode, DiscountType, LineItem
from shopflow.pricing import FLAT_SHIPPING, InvalidDiscountError, PricingEngine

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def items(*pairs):
    """items(("MUG", 2, "12.00")) -> [LineItem("MUG", 2, Decimal("12.00"))]"""
    return [LineItem(sku, qty, D(price)) for sku, qty, price in pairs]


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.engine = PricingEngine(
            [
                DiscountCode("SAVE10", DiscountType.PERCENT, D("10")),
                DiscountCode("BIGSPENDER", DiscountType.FIXED, D("20.00"), min_subtotal=D("100.00")),
                DiscountCode("SPRING", DiscountType.PERCENT, D("10"), expires_at=NOW - timedelta(days=1)),
                DiscountCode("SUMMER", DiscountType.PERCENT, D("10"), expires_at=NOW + timedelta(days=30)),
            ],
            clock=lambda: NOW,
        )

    def test_small_order_pays_shipping_and_tax(self):
        quote = self.engine.quote(items(("MUG", 2, "10.00")))
        self.assertEqual(quote.subtotal, D("20.00"))
        self.assertEqual(quote.discount, D("0.00"))
        self.assertEqual(quote.shipping, FLAT_SHIPPING)
        self.assertEqual(quote.tax, D("1.50"))
        self.assertEqual(quote.total, D("27.49"))

    def test_order_at_threshold_ships_free(self):
        quote = self.engine.quote(items(("HOODIE", 1, "50.00")))
        self.assertEqual(quote.shipping, D("0.00"))
        self.assertEqual(quote.total, D("53.75"))

    def test_percent_discount(self):
        quote = self.engine.quote(items(("SHIRT", 4, "20.00")), discount_code="SAVE10")
        self.assertEqual(quote.discount, D("8.00"))
        self.assertEqual(quote.tax, D("5.40"))
        self.assertEqual(quote.total, D("77.40"))

    def test_discount_codes_are_case_insensitive(self):
        quote = self.engine.quote(items(("SHIRT", 4, "20.00")), discount_code="save10")
        self.assertEqual(quote.discount, D("8.00"))

    def test_unknown_code_is_rejected(self):
        with self.assertRaises(InvalidDiscountError):
            self.engine.quote(items(("MUG", 1, "10.00")), discount_code="FREESTUFF")

    def test_minimum_subtotal_is_enforced(self):
        with self.assertRaises(InvalidDiscountError):
            self.engine.quote(items(("MUG", 1, "10.00")), discount_code="BIGSPENDER")

    def test_expired_code_is_rejected(self):
        with self.assertRaises(InvalidDiscountError):
            self.engine.quote(items(("SHIRT", 4, "20.00")), discount_code="SPRING")

    def test_code_with_future_expiry_is_accepted(self):
        quote = self.engine.quote(items(("SHIRT", 4, "20.00")), discount_code="SUMMER")
        self.assertEqual(quote.discount, D("8.00"))

    def test_tax_rounds_half_cents_up(self):
        # 12.60 * 0.075 = 0.945 -> must round to 0.95, not 0.94
        quote = self.engine.quote(items(("STICKERS", 3, "4.20")))
        self.assertEqual(quote.tax, D("0.95"))


if __name__ == "__main__":
    unittest.main()
