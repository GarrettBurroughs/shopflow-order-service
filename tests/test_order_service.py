import unittest
from decimal import Decimal as D

from shopflow.cart import Cart
from shopflow.inventory import InsufficientStockError, InventoryService
from shopflow.models import DiscountCode, DiscountType, OrderStatus, Product
from shopflow.order_service import InvalidTransitionError, OrderError, OrderService
from shopflow.payments import PaymentDeclinedError, PaymentGateway
from shopflow.pricing import PricingEngine
from shopflow.repository import InMemoryOrderRepository


class OrderServiceTests(unittest.TestCase):
    def setUp(self):
        catalog = {
            "MUG": Product("MUG", "Logo Mug", D("12.50")),
            "SHIRT": Product("SHIRT", "Logo T-Shirt", D("24.00")),
        }
        self.inventory = InventoryService()
        self.inventory.restock("MUG", 10)
        self.inventory.restock("SHIRT", 10)
        self.payments = PaymentGateway(credit_limits={"broke-bob": D("20.00")})
        self.service = OrderService(
            catalog=catalog,
            inventory=self.inventory,
            pricing=PricingEngine([DiscountCode("SAVE10", DiscountType.PERCENT, D("10"))]),
            payments=self.payments,
            repository=InMemoryOrderRepository(),
        )

    def _cart(self, customer_id, **skus):
        cart = Cart(customer_id)
        for sku, qty in skus.items():
            cart.add(sku, qty)
        return cart

    def test_place_order_happy_path(self):
        cart = self._cart("alice", MUG=2)
        order = self.service.place_order(cart)

        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.pricing.subtotal, D("25.00"))
        self.assertEqual(self.inventory.on_hand("MUG"), 8)
        self.assertEqual(len(self.payments.charges_for("alice")), 1)
        self.assertTrue(cart.is_empty())

    def test_empty_cart_is_rejected(self):
        with self.assertRaises(OrderError):
            self.service.place_order(Cart("alice"))

    def test_unknown_sku_is_rejected(self):
        with self.assertRaises(OrderError):
            self.service.place_order(self._cart("alice", UNICORN=1))

    def test_not_enough_stock_is_rejected(self):
        with self.assertRaises(InsufficientStockError):
            self.service.place_order(self._cart("alice", MUG=50))

    def test_declined_payment_releases_stock(self):
        with self.assertRaises(PaymentDeclinedError):
            self.service.place_order(self._cart("broke-bob", SHIRT=2))
        self.assertEqual(self.inventory.available("SHIRT"), 10)
        self.assertEqual(self.inventory.active_reservations(), 0)

    def test_retry_with_same_idempotency_key_does_not_charge_twice(self):
        first = self.service.place_order(self._cart("alice", MUG=1), idempotency_key="req-123")
        # The app timed out waiting for a response and re-sent the same request.
        retry = self.service.place_order(self._cart("alice", MUG=1), idempotency_key="req-123")

        self.assertEqual(retry.order_id, first.order_id)
        self.assertEqual(len(self.payments.charges_for("alice")), 1)
        self.assertEqual(self.inventory.on_hand("MUG"), 9)

    def test_cancel_paid_order_refunds_and_restocks(self):
        order = self.service.place_order(self._cart("alice", SHIRT=3))
        self.service.cancel_order(order.order_id)

        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertTrue(self.payments.charges[order.charge_id].refunded)
        self.assertEqual(self.inventory.on_hand("SHIRT"), 10)

    def test_ship_then_deliver(self):
        order = self.service.place_order(self._cart("alice", MUG=1))
        self.service.ship_order(order.order_id)
        self.service.mark_delivered(order.order_id)
        self.assertEqual(order.status, OrderStatus.DELIVERED)

    def test_cannot_cancel_after_shipping(self):
        order = self.service.place_order(self._cart("alice", MUG=1))
        self.service.ship_order(order.order_id)
        with self.assertRaises(InvalidTransitionError):
            self.service.cancel_order(order.order_id)

    def test_cannot_ship_a_cancelled_order(self):
        order = self.service.place_order(self._cart("alice", MUG=1))
        self.service.cancel_order(order.order_id)
        with self.assertRaises(InvalidTransitionError):
            self.service.ship_order(order.order_id)

    def test_total_revenue(self):
        self.service.place_order(self._cart("alice", MUG=2))
        self.service.place_order(self._cart("carol", SHIRT=1))
        # 25.00 + 5.99 ship + 1.88 tax  +  24.00 + 5.99 ship + 1.80 tax
        self.assertEqual(self.service.total_revenue(), D("64.66"))


if __name__ == "__main__":
    unittest.main()
