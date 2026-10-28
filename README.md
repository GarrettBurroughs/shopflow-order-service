# ShopFlow Order Service — Debugging Exercise

## Background

You've just joined the **Checkout team** at ShopFlow, a small online merch
store. This repo is the order service: it handles everything between
"Add to cart" and "Your order has shipped."

The previous owner left in a hurry. The test suite is red, and there's a pile of
bug reports in [TICKETS.md](TICKETS.md). Your job is to get the service healthy.

## How the service works

```
            Cart ──► OrderService.place_order()
                          │
      ┌───────────────────┼────────────────────┬──────────────────┐
      ▼                   ▼                    ▼                  ▼
 InventoryService    PricingEngine       PaymentGateway    OrderRepository
 reserve / commit    subtotal, discount  charge / refund   save / lookup /
 / release stock     shipping, tax                         order history
```

| File | Responsibility |
|---|---|
| `shopflow/models.py` | Data classes: `Product`, `LineItem`, `Order`, `OrderStatus`, ... |
| `shopflow/cart.py` | A customer's shopping cart |
| `shopflow/inventory.py` | Stock levels and checkout reservations ("holds") |
| `shopflow/pricing.py` | Subtotal, discount codes, shipping, sales tax |
| `shopflow/payments.py` | Fake card processor (charge / refund) |
| `shopflow/repository.py` | In-memory order storage and order history |
| `shopflow/order_service.py` | Ties it all together: checkout, cancel, ship, reporting |
| `main.py` | Smoke-test script that runs realistic customer scenarios |

**The comments and docstrings describe how the system is *supposed* to
behave.** For this exercise, treat them as the spec. When the code and the
comment disagree, the comment is right.

## Setup

Requires Python 3.10+. No third-party packages are needed.

```bash
python main.py                      # run the demo scenarios
python -m unittest -v               # run every test
python -m unittest tests.test_cart  # run one test file
python -m unittest tests.test_cart.CartTests.test_remove_whole_line   # run one test
```

(If you have pytest installed, `pytest -v` works too.)

## Your tasks

1. **Get the test suite passing.** Don't edit the existing tests. They're
   believed to be correct.
2. **Work the tickets in [TICKETS.md](TICKETS.md).** Several describe bugs the tests
   don't cover. There are more bugs than failing tests.
3. **Keep notes** in a `NOTES.md` as you go. For each bug, write:
   - Symptom: what was observed
   - Root cause: the actual mistake, with file and line
   - Fix: what you changed
   - Prevention: the test you added, or what would have caught it earlier
4. **Stretch:** write a regression test for each ticket you fix.

Suggested timebox: about 90 minutes. You don't need to finish everything.
Your reasoning and notes matter more than the count.

## Tips

- Read tracebacks from the **bottom up**. The last frame shows where it
  blew up; the frames above show how it got there.
- Several failures can come from **one root cause**. If many things are broken,
  look for the earliest thing that goes wrong.
- `breakpoint()` drops you into the debugger anywhere. `LOG_LEVEL=INFO python main.py`
  turns on the service's logs.
- Make small changes and re-run the tests after each one.
