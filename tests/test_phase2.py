"""Phase 2 regression tests for FIFO depletion and loss-cost accounting."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database as db


class PhaseTwoInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_file = db.DB_FILE
        db.DB_FILE = os.path.join(self.temp_dir.name, "test.sqlite")
        db.init_db()
        self.vegetable_id = db.add_vegetable(
            name="Test Spinach",
            category="Leafy Greens",
            unit="kg",
            shelf_life_days=10,
            reorder_threshold_kg=2,
            optimal_temp_celsius=4,
        )
        today = datetime.now(db.BUSINESS_TIMEZONE).date()
        self.today = today.strftime("%Y-%m-%d")
        first_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        second_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        self.first_batch_id = db.record_purchase(
            self.vegetable_id, first_date, 3, 10, "LOT-OLD",
            (today + timedelta(days=8)).strftime("%Y-%m-%d")
        )
        self.second_batch_id = db.record_purchase(
            self.vegetable_id, second_date, 4, 20, "LOT-NEW",
            (today + timedelta(days=9)).strftime("%Y-%m-%d")
        )

    def tearDown(self):
        db.DB_FILE = self.previous_db_file
        self.temp_dir.cleanup()

    def test_sale_depletes_oldest_batch_and_calculates_margin(self):
        sale_id = db.record_sale(self.vegetable_id, self.today, 4, 30)
        sale = next(row for row in db.get_all_sales() if row["id"] == sale_id)

        self.assertEqual(sale["revenue"], 120)
        self.assertEqual(sale["cost_of_goods_sold"], 50)
        self.assertEqual(sale["gross_margin"], 70)

        batches = db.get_batch_balances(self.vegetable_id)
        remaining = {row["batch_code"]: row["remaining_kg"] for row in batches}
        self.assertEqual(remaining["LOT-OLD"], 0)
        self.assertEqual(remaining["LOT-NEW"], 3)

    def test_wastage_uses_remaining_fifo_purchase_cost(self):
        db.record_sale(self.vegetable_id, self.today, 4, 30)
        wastage_id = db.record_wastage(
            self.vegetable_id, self.today, 2, "Transit damage",
            notes="Bruised during unloading"
        )
        wastage = next(row for row in db.get_all_wastage() if row["id"] == wastage_id)

        self.assertEqual(wastage["loss_cost"], 40)
        self.assertEqual(wastage["notes"], "Bruised during unloading")
        self.assertEqual(db.calculate_live_stock(self.vegetable_id), 1)

    def test_rejected_overstock_writes_do_not_change_the_ledger(self):
        with self.assertRaisesRegex(ValueError, "Insufficient eligible stock"):
            db.record_sale(self.vegetable_id, self.today, 8, 30)
        with self.assertRaisesRegex(ValueError, "Wastage exceeds eligible stock"):
            db.record_wastage(self.vegetable_id, self.today, 8, "Rotting")

        self.assertEqual(db.calculate_live_stock(self.vegetable_id), 7)
        self.assertEqual(db.get_all_sales(), [])
        self.assertEqual(db.get_all_wastage(), [])

    def test_phase_one_sales_are_backfilled_to_fifo_batches(self):
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO sales
                   (veg_id, sale_date, quantity_kg, selling_price_per_kg, revenue)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.vegetable_id, self.today, 2, 30, 60),
            )
            conn.commit()

        db.init_db()
        sale = db.get_all_sales()[0]
        self.assertEqual(sale["cost_of_goods_sold"], 20)
        balances = {row["batch_code"]: row["remaining_kg"] for row in db.get_batch_balances(self.vegetable_id)}
        self.assertEqual(balances["LOT-OLD"], 1)
        self.assertEqual(balances["LOT-NEW"], 4)

    def test_expired_stock_cannot_be_sold_but_can_be_written_off(self):
        today = datetime.now(db.BUSINESS_TIMEZONE).date()
        old_date = (today - timedelta(days=20)).strftime("%Y-%m-%d")
        expired_date = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        db.record_purchase(
            self.vegetable_id, old_date, 2, 10, "LOT-EXPIRED", expired_date
        )

        with self.assertRaisesRegex(ValueError, "Insufficient eligible stock"):
            db.record_sale(self.vegetable_id, self.today, 8, 30)
        self.assertEqual(db.get_stock_overview()[0]["available_for_sale_kg"], 7)

        db.record_wastage(self.vegetable_id, self.today, 2, "Rotting")
        self.assertEqual(db.calculate_live_stock(self.vegetable_id), 7)


if __name__ == "__main__":
    unittest.main()
