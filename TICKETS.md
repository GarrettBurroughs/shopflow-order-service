# Open Tickets — Checkout Team

> Ticket numbers come from the reporting team. Priority is the reporter's
> best guess. Feel free to disagree with it.

---

### SHOP-108 · P0 · "I can see someone else's stuff in my cart"
**Reporter:** Customer Support

Several customers say items they never added are showing up in their cart.
One customer checked out and was charged for a hoodie they never ordered.
Another said their cart emptied by itself right after someone else placed an order.

---

### SHOP-101 · P1 · Stock disappears after a failed promo code
**Reporter:** Customer Support

A customer tried to buy 2 t-shirts with the promo code `SUMMER`. They got
"Discount code 'SUMMER' has expired" (which is fine, the sale ended). They tried
twice more and then gave up.

Afterwards the warehouse dashboard showed t-shirt **availability down by 6**,
but no order exists. Ops says the reservation cleanup job should have returned
those units within 15 minutes. It's been hours. (Possibly related to SHOP-102?)

---

### SHOP-102 · P1 · Reservation cleanup job crashing
**Reporter:** SRE / on-call

The background job that runs `InventoryService.expire_stale_reservations()`
every minute has failed on most runs since last Tuesday. It succeeds when
nothing has expired. Stack trace from the job logs:

```
Traceback (most recent call last):
  File "jobs/reservation_sweeper.py", line 18, in run
    released = inventory.expire_stale_reservations()
  File "shopflow/inventory.py", line 125, in expire_stale_reservations
    for reservation_id, reservation in self._reservations.items():
RuntimeError: dictionary changed size during iteration
```

---

### SHOP-103 · P2 · Free shipping given on orders under $50
**Reporter:** Finance

Policy: shipping is free when the order is $50 or more **after discounts**.

Example order: 1 Zip Hoodie ($45.00) + 2 Sticker Packs ($8.40) = $53.40, with
code `WELCOME10` ($10 off), so $43.40 after the discount. The customer was charged
**$0.00 shipping**. They should have paid $5.99.

---

### SHOP-104 · P2 · Checkout crashes with the VIP25 code on small orders
**Reporter:** Mobile team

Our VIP customers get a `VIP25` code worth $25 off. When a VIP buys just a mug
($12.50) with it, checkout fails with a 500 error:

```
ValueError: Charge amount must be positive, got -7.45
```

Expected: the discount covers the whole $12.50, so the customer pays only shipping
($5.99). Also, the mug they were trying to buy seems to stay "held" after the error.

---

### SHOP-105 · P1 · Security: negative quantities accepted
**Reporter:** Security team (found during a pen test)

The tester sent an add-to-cart request with `quantity: -3` for Logo Mugs,
alongside 1 Zip Hoodie. Checkout succeeded with a **total of $14.05** for a $45
hoodie. Inventory also shows *more* mugs on hand afterwards than before.

---

### SHOP-106 · P2 · Finance dashboard revenue doesn't match the bank
**Reporter:** Finance

Revenue from `total_revenue()` is consistently higher than what actually
settles in our bank account. The difference seems to match the value of orders
that were cancelled and refunded.

---

### SHOP-107 · P2 · Order history is empty for most customers
**Reporter:** Mobile team

The "My Orders" screen calls `order_history(customer_id, page=1, page_size=20)`.
A customer with 3 orders sees an **empty list**. Customers with lots of orders
see a list, but their most recent orders are missing from the top.
