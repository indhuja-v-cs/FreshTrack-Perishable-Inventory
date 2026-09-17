"""
database.py - SQLite Database Engine for Perishable Vegetable Inventory
------------------------------------------------------------------------
Handles schema definition, ACID transactions, data persistence,
and real-time stock computation.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perishable_inventory.db")


def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Creates the database schema if tables do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Vegetables Master Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vegetables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT 'Fresh',
                unit TEXT NOT NULL DEFAULT 'kg',
                shelf_life_days INTEGER NOT NULL,
                reorder_threshold_kg REAL NOT NULL DEFAULT 10.0,
                optimal_temp_celsius REAL NOT NULL DEFAULT 10.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Purchase / Inward Stock Batches Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                veg_id INTEGER NOT NULL,
                purchase_date TEXT NOT NULL,
                quantity_kg REAL NOT NULL,
                cost_per_kg REAL NOT NULL,
                batch_code TEXT NOT NULL UNIQUE,
                expiry_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (veg_id) REFERENCES vegetables(id) ON DELETE CASCADE
            )
        """)

        # 3. Sales Transactions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                veg_id INTEGER NOT NULL,
                sale_date TEXT NOT NULL,
                quantity_kg REAL NOT NULL,
                selling_price_per_kg REAL NOT NULL,
                revenue REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (veg_id) REFERENCES vegetables(id) ON DELETE CASCADE
            )
        """)

        # 4. Spoilage / Wastage Ledger Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wastage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                veg_id INTEGER NOT NULL,
                record_date TEXT NOT NULL,
                quantity_kg REAL NOT NULL,
                reason TEXT NOT NULL,
                loss_cost REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (veg_id) REFERENCES vegetables(id) ON DELETE CASCADE
            )
        """)

        conn.commit()


# ==========================================
# VEGETABLE MASTER OPERATIONS
# ==========================================

def add_vegetable(
    name: str,
    category: str,
    unit: str,
    shelf_life_days: int,
    reorder_threshold_kg: float,
    optimal_temp_celsius: float = 10.0
) -> int:
    """Adds a new vegetable to the master catalogue."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vegetables (name, category, unit, shelf_life_days, reorder_threshold_kg, optimal_temp_celsius)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name.strip(), category.strip(), unit.strip(), int(shelf_life_days), float(reorder_threshold_kg), float(optimal_temp_celsius)))
        conn.commit()
        return cursor.lastrowid


def get_all_vegetables() -> List[Dict[str, Any]]:
    """Returns a list of all vegetables in the master table."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vegetables ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]


def get_vegetable_by_id(veg_id: int) -> Optional[Dict[str, Any]]:
    """Fetches vegetable metadata by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vegetables WHERE id = ?", (veg_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ==========================================
# INWARD STOCK / PURCHASE OPERATIONS
# ==========================================

def record_purchase(
    veg_id: int,
    purchase_date: str,
    quantity_kg: float,
    cost_per_kg: float,
    batch_code: Optional[str] = None,
    expiry_date: Optional[str] = None
) -> int:
    """
    Records an incoming shipment of vegetables.
    Automatically computes expiry_date if not provided using the vegetable's shelf life.
    """
    veg = get_vegetable_by_id(veg_id)
    if not veg:
        raise ValueError(f"Vegetable with ID {veg_id} does not exist.")

    p_date = datetime.strptime(purchase_date, "%Y-%m-%d")

    # Calculate expiry date if not provided
    if not expiry_date:
        calc_expiry = p_date + timedelta(days=veg["shelf_life_days"])
        expiry_date = calc_expiry.strftime("%Y-%m-%d")

    # Generate batch code if not provided
    if not batch_code:
        sanitized_name = "".join(c for c in veg["name"] if c.isalnum())[:3].upper()
        time_part = datetime.now().strftime("%H%M%S")
        batch_code = f"BAT-{sanitized_name}-{purchase_date.replace('-', '')}-{time_part}"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO purchases (veg_id, purchase_date, quantity_kg, cost_per_kg, batch_code, expiry_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (veg_id, purchase_date, float(quantity_kg), float(cost_per_kg), batch_code, expiry_date))
        conn.commit()
        return cursor.lastrowid


def get_all_purchases() -> List[Dict[str, Any]]:
    """Returns all purchase batches joined with vegetable names."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, v.name as veg_name, v.category, v.unit
            FROM purchases p
            JOIN vegetables v ON p.veg_id = v.id
            ORDER BY p.purchase_date DESC, p.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


# ==========================================
# SALES OPERATIONS
# ==========================================

def record_sale(
    veg_id: int,
    sale_date: str,
    quantity_kg: float,
    selling_price_per_kg: float
) -> int:
    """Records a sales transaction and checks stock availability."""
    current_stock = calculate_live_stock(veg_id)
    if float(quantity_kg) > current_stock:
        raise ValueError(f"Insufficient stock! Available: {current_stock:.2f} kg, Requested: {quantity_kg:.2f} kg.")

    revenue = round(float(quantity_kg) * float(selling_price_per_kg), 2)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sales (veg_id, sale_date, quantity_kg, selling_price_per_kg, revenue)
            VALUES (?, ?, ?, ?, ?)
        """, (veg_id, sale_date, float(quantity_kg), float(selling_price_per_kg), revenue))
        conn.commit()
        return cursor.lastrowid


def get_all_sales() -> List[Dict[str, Any]]:
    """Returns all sales transactions joined with vegetable names."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, v.name as veg_name, v.unit
            FROM sales s
            JOIN vegetables v ON s.veg_id = v.id
            ORDER BY s.sale_date DESC, s.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


# ==========================================
# SPOILAGE / WASTAGE OPERATIONS
# ==========================================

def record_wastage(
    veg_id: int,
    record_date: str,
    quantity_kg: float,
    reason: str,
    loss_cost: Optional[float] = None
) -> int:
    """
    Records spoiled/unsold vegetables thrown away.
    If loss_cost is not provided, calculates it from latest purchase cost.
    """
    current_stock = calculate_live_stock(veg_id)
    if float(quantity_kg) > current_stock:
        raise ValueError(f"Wastage cannot exceed current stock ({current_stock:.2f} kg).")

    if loss_cost is None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cost_per_kg FROM purchases
                WHERE veg_id = ?
                ORDER BY purchase_date DESC, id DESC LIMIT 1
            """, (veg_id,))
            row = cursor.fetchone()
            latest_cost = row["cost_per_kg"] if row else 20.0
            loss_cost = round(float(quantity_kg) * latest_cost, 2)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO wastage (veg_id, record_date, quantity_kg, reason, loss_cost)
            VALUES (?, ?, ?, ?, ?)
        """, (veg_id, record_date, float(quantity_kg), reason.strip(), float(loss_cost)))
        conn.commit()
        return cursor.lastrowid


def get_all_wastage() -> List[Dict[str, Any]]:
    """Returns all wastage entries joined with vegetable names."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.*, v.name as veg_name, v.unit
            FROM wastage w
            JOIN vegetables v ON w.veg_id = v.id
            ORDER BY w.record_date DESC, w.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


# ==========================================
# LIVE STOCK & INVENTORY MATHEMATICAL ENGINE
# ==========================================

def calculate_live_stock(veg_id: int) -> float:
    """
    Computes real-time available stock using the fundamental balance equation:
    Current Stock = Total Purchased - Total Sold - Total Wasted
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM purchases WHERE veg_id = ?", (veg_id,))
        total_purchased = cursor.fetchone()["total"]

        cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM sales WHERE veg_id = ?", (veg_id,))
        total_sold = cursor.fetchone()["total"]

        cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM wastage WHERE veg_id = ?", (veg_id,))
        total_wasted = cursor.fetchone()["total"]

        stock = total_purchased - total_sold - total_wasted
        return max(0.0, round(stock, 2))


def get_stock_overview() -> List[Dict[str, Any]]:
    """
    Produces a comprehensive inventory health summary for all vegetables.
    Calculates current stock, total inward, total outward, nearest expiry date,
    days remaining, and status indicators.
    """
    vegetables = get_all_vegetables()
    overview = []
    today = datetime.now().date()

    with get_connection() as conn:
        cursor = conn.cursor()

        for veg in vegetables:
            vid = veg["id"]

            # Quantities
            cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM purchases WHERE veg_id = ?", (vid,))
            total_purchased = cursor.fetchone()["total"]

            cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM sales WHERE veg_id = ?", (vid,))
            total_sold = cursor.fetchone()["total"]

            cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM wastage WHERE veg_id = ?", (vid,))
            total_wasted = cursor.fetchone()["total"]

            current_stock = max(0.0, round(total_purchased - total_sold - total_wasted, 2))

            # Nearest active batch expiry
            cursor.execute("""
                SELECT expiry_date FROM purchases
                WHERE veg_id = ?
                ORDER BY expiry_date ASC LIMIT 1
            """, (vid,))
            exp_row = cursor.fetchone()

            nearest_expiry = exp_row["expiry_date"] if exp_row else "N/A"
            days_to_expiry = None

            if exp_row:
                exp_date = datetime.strptime(exp_row["expiry_date"], "%Y-%m-%d").date()
                days_to_expiry = (exp_date - today).days

            # Determine Health Status
            if current_stock == 0.0:
                status = "OUT OF STOCK"
                status_color = "red"
            elif days_to_expiry is not None and days_to_expiry < 0:
                status = "EXPIRED BATCH"
                status_color = "red"
            elif days_to_expiry is not None and days_to_expiry <= 1:
                status = "EXPIRING SOON"
                status_color = "orange"
            elif current_stock <= veg["reorder_threshold_kg"]:
                status = "LOW STOCK"
                status_color = "amber"
            else:
                status = "HEALTHY"
                status_color = "green"

            overview.append({
                "id": vid,
                "name": veg["name"],
                "category": veg["category"],
                "unit": veg["unit"],
                "shelf_life_days": veg["shelf_life_days"],
                "current_stock_kg": current_stock,
                "reorder_threshold_kg": veg["reorder_threshold_kg"],
                "total_purchased_kg": round(total_purchased, 2),
                "total_sold_kg": round(total_sold, 2),
                "total_wasted_kg": round(total_wasted, 2),
                "nearest_expiry": nearest_expiry,
                "days_to_expiry": days_to_expiry,
                "status": status,
                "status_color": status_color
            })

    return overview


def reset_database() -> None:
    """Drops all tables and recreates clean schema."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS wastage")
        cursor.execute("DROP TABLE IF EXISTS sales")
        cursor.execute("DROP TABLE IF EXISTS purchases")
        cursor.execute("DROP TABLE IF EXISTS vegetables")
        conn.commit()
    init_db()
