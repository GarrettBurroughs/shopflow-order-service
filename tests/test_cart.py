import unittest

from shopflow.cart import Cart


class CartTests(unittest.TestCase):
    def test_add_merges_same_sku_into_one_line(self):
        cart = Cart("alice")
        cart.add("MUG", 1)
        cart.add("MUG", 2)
        self.assertEqual(cart.items, {"MUG": 3})

    def test_add_rejects_non_integer_quantity(self):
        cart = Cart("alice")
        with self.assertRaises(ValueError):
            cart.add("MUG", 1.5)

    def test_remove_partial_quantity(self):
        cart = Cart("alice")
        cart.add("SHIRT", 5)
        cart.remove("SHIRT", 2)
        self.assertEqual(cart.items["SHIRT"], 3)

    def test_remove_whole_line(self):
        cart = Cart("alice")
        cart.add("SHIRT", 5)
        cart.remove("SHIRT")
        self.assertNotIn("SHIRT", cart.items)

    def test_remove_missing_sku_is_noop(self):
        cart = Cart("alice")
        cart.remove("DOES-NOT-EXIST")  # must not raise

    def test_two_customers_have_separate_carts(self):
        alice = Cart("alice")
        bob = Cart("bob")
        alice.add("MUG", 1)
        self.assertEqual(bob.items, {}, "Bob's cart should not contain Alice's items")


if __name__ == "__main__":
    unittest.main()
