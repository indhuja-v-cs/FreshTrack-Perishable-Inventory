"""
seed_data.py - Realistic Perishable Vegetable Inventory Sample Seeder
---------------------------------------------------------------------
Populates the SQLite database with realistic perishable items, shelf lives,
inward batches, and initial transaction logs for demo and testing.
"""

from datetime import datetime, timedelta
import database as db


def seed_database(reset: bool = True):
    """Initializes and seeds the database with realistic inventory data."""
    if reset:
        print("Resetting database tables...")
        db.reset_database()
    else:
        db.init_db()

    # Check if already seeded
    existing_veg = db.get_all_vegetables()
    if existing_veg and not reset:
        print(f"Database already contains {len(existing_veg)} vegetables. Skipping seed.")
        return

    print("Seeding vegetable master catalog...")
    today = datetime.now().date()

    vegetable_catalog = [
        {"name": "Spinach (Palak)", "category": "Leafy Greens", "unit": "kg", "shelf_life_days": 2, "reorder_threshold_kg": 10.0, "optimal_temp_celsius": 4.0},
        {"name": "Coriander (Dhaniya)", "category": "Leafy Greens", "unit": "kg", "shelf_life_days": 3, "reorder_threshold_kg": 5.0, "optimal_temp_celsius": 4.0},
        {"name": "Tomato (Tamatar)", "category": "Fruit Vegetable", "unit": "kg", "shelf_life_days": 6, "reorder_threshold_kg": 25.0, "optimal_temp_celsius": 12.0},
        {"name": "Cauliflower (Phool Gobi)", "category": "Cruciferous", "unit": "kg", "shelf_life_days": 5, "reorder_threshold_kg": 15.0, "optimal_temp_celsius": 5.0},
        {"name": "Bell Pepper (Shimla Mirch)", "category": "Fruit Vegetable", "unit": "kg", "shelf_life_days": 7, "reorder_threshold_kg": 10.0, "optimal_temp_celsius": 8.0},
        {"name": "Carrot (Gajar)", "category": "Root Vegetable", "unit": "kg", "shelf_life_days": 10, "reorder_threshold_kg": 15.0, "optimal_temp_celsius": 4.0},
        {"name": "Onion (Pyaaz)", "category": "Root & Bulb", "unit": "kg", "shelf_life_days": 30, "reorder_threshold_kg": 30.0, "optimal_temp_celsius": 20.0},
        {"name": "Potato (Aaloo)", "category": "Tubers", "unit": "kg", "shelf_life_days": 45, "reorder_threshold_kg": 40.0, "optimal_temp_celsius": 15.0},
    ]

    veg_ids = {}
    for veg in vegetable_catalog:
        vid = db.add_vegetable(
            name=veg["name"],
            category=veg["category"],
            unit=veg["unit"],
            shelf_life_days=veg["shelf_life_days"],
            reorder_threshold_kg=veg["reorder_threshold_kg"],
            optimal_temp_celsius=veg["optimal_temp_celsius"]
        )
        veg_ids[veg["name"]] = vid

    print("Seeding inward purchase batches...")
    purchases = [
        # Spinach: purchased 1 day ago, 30 kg, shelf life 2 days -> expires tomorrow!
        {"veg_name": "Spinach (Palak)", "days_ago": 1, "qty": 30.0, "cost": 20.0},
        # Coriander: purchased today, 15 kg
        {"veg_name": "Coriander (Dhaniya)", "days_ago": 0, "qty": 15.0, "cost": 25.0},
        # Tomato: purchased 2 days ago, 80 kg
        {"veg_name": "Tomato (Tamatar)", "days_ago": 2, "qty": 80.0, "cost": 32.0},
        # Cauliflower: purchased 2 days ago, 35 kg
        {"veg_name": "Cauliflower (Phool Gobi)", "days_ago": 2, "qty": 35.0, "cost": 28.0},
        # Bell Pepper: purchased 1 day ago, 25 kg
        {"veg_name": "Bell Pepper (Shimla Mirch)", "days_ago": 1, "qty": 25.0, "cost": 45.0},
        # Carrot: purchased 3 days ago, 40 kg
        {"veg_name": "Carrot (Gajar)", "days_ago": 3, "qty": 40.0, "cost": 30.0},
        # Onion: purchased 6 days ago, 150 kg
        {"veg_name": "Onion (Pyaaz)", "days_ago": 6, "qty": 150.0, "cost": 22.0},
        # Potato: purchased 6 days ago, 200 kg
        {"veg_name": "Potato (Aaloo)", "days_ago": 6, "qty": 200.0, "cost": 18.0},
    ]

    for p in purchases:
        p_date = (today - timedelta(days=p["days_ago"])).strftime("%Y-%m-%d")
        db.record_purchase(
            veg_id=veg_ids[p["veg_name"]],
            purchase_date=p_date,
            quantity_kg=p["qty"],
            cost_per_kg=p["cost"]
        )

    print("Seeding sales records...")
    sales = [
        {"veg_name": "Spinach (Palak)", "days_ago": 0, "qty": 18.0, "price": 35.0},
        {"veg_name": "Tomato (Tamatar)", "days_ago": 1, "qty": 45.0, "price": 48.0},
        {"veg_name": "Cauliflower (Phool Gobi)", "days_ago": 1, "qty": 20.0, "price": 40.0},
        {"veg_name": "Bell Pepper (Shimla Mirch)", "days_ago": 0, "qty": 10.0, "price": 65.0},
        {"veg_name": "Carrot (Gajar)", "days_ago": 1, "qty": 15.0, "price": 42.0},
        {"veg_name": "Onion (Pyaaz)", "days_ago": 2, "qty": 60.0, "price": 32.0},
        {"veg_name": "Potato (Aaloo)", "days_ago": 2, "qty": 80.0, "price": 28.0},
    ]

    for s in sales:
        s_date = (today - timedelta(days=s["days_ago"])).strftime("%Y-%m-%d")
        db.record_sale(
            veg_id=veg_ids[s["veg_name"]],
            sale_date=s_date,
            quantity_kg=s["qty"],
            selling_price_per_kg=s["price"]
        )

    print("Seeding recorded spoilage / wastage logs...")
    wastages = [
        {"veg_name": "Spinach (Palak)", "days_ago": 0, "qty": 2.0, "reason": "Yellowing & wilted foliage", "cost": 40.0},
        {"veg_name": "Tomato (Tamatar)", "days_ago": 0, "qty": 3.0, "reason": "Soft bruise and overripe transit damage", "cost": 96.0},
        {"veg_name": "Cauliflower (Phool Gobi)", "days_ago": 0, "qty": 1.5, "reason": "Browning fungus spots", "cost": 42.0},
    ]

    for w in wastages:
        w_date = (today - timedelta(days=w["days_ago"])).strftime("%Y-%m-%d")
        db.record_wastage(
            veg_id=veg_ids[w["veg_name"]],
            record_date=w_date,
            quantity_kg=w["qty"],
            reason=w["reason"],
            loss_cost=w["cost"]
        )

    print("Seed completed successfully! All tables populated.")


if __name__ == "__main__":
    seed_database(reset=True)
    print("\n--- Current Inventory Status Summary ---")
    overview = db.get_stock_overview()
    for item in overview:
        print(f"[{item['status']}] {item['name']}: {item['current_stock_kg']} {item['unit']} in stock | Nearest Expiry: {item['nearest_expiry']} ({item['days_to_expiry']} days)")
