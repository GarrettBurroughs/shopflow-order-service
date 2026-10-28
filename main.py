"""Local smoke test: wires up the service with sample data and runs a few
realistic customer journeys, printing what happens.

    python main.py

Each scenario says what SHOULD happen. Compare that to what you see.
Set LOG_LEVEL=INFO to see the service's internal logs.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from decimal import Decimal as D

from shopflow.cart import Cart
from shopflow.inventory import InventoryService
from shopflow.models import DiscountCode, DiscountType, Order, Product, utc_now
from shopflow.order_service import OrderService
from shopflow.payments import PaymentGateway
from shopflow.pricing import PricingEngine
from shopflow.repository import InMemoryOrderRepository

CATALOG = {
    "MUG": Product("MUG", "Logo Mug", D("12.50")),
    "TSHIRT": Product("TSHIRT", "Logo T-Shirt", D("24.00")),
    "HOODIE": Product("HOODIE", "Zip Hoodie", D("45.00")),
    "STICKERS": Product("STICKERS", "Sticker Pack", D("4.20")),
    "POSTER": Product("POSTER", "Limited Edition Poster", D("30.00")),
}

STARTING_STOCK = {"MUG": 50, "TSHIRT": 40, "HOODIE": 20, "STICKERS": 200, "POSTER": 1}

DISCOUNT_CODES = [
    DiscountCode("SAVE15", DiscountType.PERCENT, D("15")),
    DiscountCode("WELCOME10", DiscountType.FIXED, D("10.00"), min_subtotal=D("20.00")),
    DiscountCode("VIP25", DiscountType.FIXED, D("25.00")),
    DiscountCode("FALLSALE", DiscountType.PERCENT, D("20"), expires_at=utc_now() + timedelta(days=30)),
    DiscountCode("SUMMER", DiscountType.PERCENT, D("20"), expires_at=utc_now() - timedelta(days=60)),
]


def build_service() -> tuple[OrderService, InventoryService, PaymentGateway]:
    inventory = InventoryService()
    for sku, qty in STARTING_STOCK.items():
        inventory.restock(sku, qty)
    payments = PaymentGateway()
    service = OrderService(
        catalog=CATALOG,
        inventory=inventory,
        pricing=PricingEngine(DISCOUNT_CODES),
        payments=payments,
        repository=InMemoryOrderRepository(),
    )
    return service, inventory, payments


def print_receipt(order: Order) -> None:
    p = order.pricing
    print(f"  {order.order_id} [{order.status.value}] for {order.customer_id}")
    for item in order.items:
        print(f"    {item.quantity} x {CATALOG[item.sku].name:<24} ${item.line_total:>8}")
    print(f"    {'Subtotal':<28} ${p.subtotal:>8}")
    if p.discount:
        print(f"    {'Discount (' + str(order.discount_code) + ')':<28} -${p.discount:>7}")
    print(f"    {'Shipping':<28} ${p.shipping:>8}")
    print(f"    {'Tax':<28} ${p.tax:>8}")
    print(f"    {'TOTAL':<28} ${p.total:>8}")


def scenario(title: str, expected: str):
    """Decorator that prints a header and catches errors so one failure doesn't stop the demo."""
    def wrap(fn):
        def run(*args):
            print(f"\n=== {title}")
            print(f"    expected: {expected}")
            try:
                fn(*args)
            except Exception as exc:  # noqa: BLE001 - demo script, show everything
                print(f"  ERROR: {type(exc).__name__}: {exc}")
        return run
    return wrap


@scenario("1. Alice and Bob fill their carts",
          "Alice has 2 mugs + 1 sticker pack; Bob has 1 hoodie")
def fill_carts(alice: Cart, bob: Cart):
    alice.add("MUG", 2)
    alice.add("STICKERS", 1)
    bob.add("HOODIE", 1)
    print(f"  alice: {alice.items}")
    print(f"  bob:   {bob.items}")


@scenario("2. Alice checks out with SAVE15",
          "15% off a $29.20 subtotal, flat shipping, order is PAID")
def alice_checkout(service: OrderService, alice: Cart):
    order = service.place_order(alice, discount_code="SAVE15", idempotency_key="alice-checkout-1")
    print_receipt(order)


@scenario("3. Dana buys the one and only limited-edition poster",
          "Order succeeds and the poster is now sold out")
def dana_buys_poster(service: OrderService, inventory: InventoryService):
    dana = Cart("dana")
    dana.add("POSTER", 1)
    order = service.place_order(dana)
    print_receipt(order)
    print(f"  posters left: {inventory.available('POSTER')}")


@scenario("4. Erin uses the FALLSALE code (valid for another 30 days)",
          "20% off 2 t-shirts")
def erin_fallsale(service: OrderService):
    erin = Cart("erin")
    erin.add("TSHIRT", 2)
    order = service.place_order(erin, discount_code="FALLSALE")
    print_receipt(order)


@scenario("5. Frank buys 3 sticker packs, no code",
          "Subtotal $12.60, tax $0.95 (0.945 rounds up), total $19.54")
def frank_stickers(service: OrderService):
    frank = Cart("frank")
    frank.add("STICKERS", 3)
    print_receipt(service.place_order(frank))


@scenario("6. Gina orders, then cancels before it ships",
          "Order CANCELLED, charge refunded, hoodie back in stock (20 available)")
def gina_cancels(service: OrderService, inventory: InventoryService, payments: PaymentGateway):
    gina = Cart("gina")
    gina.add("HOODIE", 1)
    order = service.place_order(gina)
    service.cancel_order(order.order_id)
    print(f"  {order.order_id} status: {order.status.value}")
    print(f"  refunded: {payments.charges[order.charge_id].refunded}")
    print(f"  hoodies available: {inventory.available('HOODIE')}")


@scenario("7. Alice views her order history",
          "Her order from scenario 2 is on page 1")
def alice_history(service: OrderService):
    history = service.order_history("alice", page=1)
    print(f"  page 1: {[o.order_id for o in history]}")


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"),
                        format="%(levelname)s %(name)s: %(message)s")
    service, inventory, payments = build_service()

    alice = Cart("alice")
    bob = Cart("bob")

    fill_carts(alice, bob)
    alice_checkout(service, alice)
    dana_buys_poster(service, inventory)
    erin_fallsale(service)
    frank_stickers(service)
    gina_cancels(service, inventory, payments)
    alice_history(service)

    print(f"\nRevenue reported to Finance: ${service.total_revenue()}")
    print("Done.")


if __name__ == "__main__":
    main()
