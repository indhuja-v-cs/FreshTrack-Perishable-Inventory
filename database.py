"""
database.py - SQLite Database Engine for Perishable Vegetable Inventory
------------------------------------------------------------------------
Handles schema definition, ACID transactions, data persistence,
and real-time stock computation.
"""

import sqlite3
import os
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Iterator
from contextlib import contextmanager
from zoneinfo import ZoneInfo

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perishable_inventory.db")
BUSINESS_TIMEZONE = ZoneInfo("Asia/Kolkata")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Returns a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (veg_id) REFERENCES vegetables(id) ON DELETE CASCADE
            )
        """)

        # Phase 2 keeps an auditable record of which inward batches each
        # sale/write-off consumed. Existing Phase 1 databases are upgraded in
        # place; their old transactions are assigned FIFO batch allocations.
        wastage_columns = {
            row["name"] for row in cursor.execute("PRAGMA table_info(wastage)")
        }
        if "notes" not in wastage_columns:
            cursor.execute("ALTER TABLE wastage ADD COLUMN notes TEXT")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sale_batch_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                purchase_id INTEGER NOT NULL,
                quantity_kg REAL NOT NULL CHECK (quantity_kg > 0),
                FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
                FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wastage_batch_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wastage_id INTEGER NOT NULL,
                purchase_id INTEGER NOT NULL,
                quantity_kg REAL NOT NULL CHECK (quantity_kg > 0),
                FOREIGN KEY (wastage_id) REFERENCES wastage(id) ON DELETE CASCADE,
                FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sale_allocations_purchase
            ON sale_batch_allocations(purchase_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_wastage_allocations_purchase
            ON wastage_batch_allocations(purchase_id)
        """)
        _backfill_legacy_batch_allocations(cursor)

        conn.commit()


def _remaining_batches(cursor: sqlite3.Cursor, veg_id: int, on_or_before: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return batch balances in FIFO order, including the true purchase cost."""
    date_filter = "AND p.purchase_date <= ?" if on_or_before else ""
    params: tuple = (veg_id, on_or_before) if on_or_before else (veg_id,)
    cursor.execute(f"""
        SELECT
            p.id, p.veg_id, p.batch_code, p.purchase_date, p.expiry_date,
            p.quantity_kg AS purchased_kg, p.cost_per_kg,
            p.quantity_kg
              - COALESCE((SELECT SUM(a.quantity_kg)
                          FROM sale_batch_allocations a WHERE a.purchase_id = p.id), 0)
              - COALESCE((SELECT SUM(a.quantity_kg)
                          FROM wastage_batch_allocations a WHERE a.purchase_id = p.id), 0)
              AS remaining_kg
        FROM purchases p
        WHERE p.veg_id = ? {date_filter}
        ORDER BY p.purchase_date ASC, p.id ASC
    """, params)
    return [dict(row) for row in cursor.fetchall()]


def _fifo_plan(
    cursor: sqlite3.Cursor,
    veg_id: int,
    transaction_date: str,
    quantity_kg: float,
    exclude_expired: bool = False
) -> List[Dict[str, Any]]:
    """Plan a first-in-first-out depletion without changing the database."""
    left = float(quantity_kg)
    plan = []
    for batch in _remaining_batches(cursor, veg_id, transaction_date):
        if exclude_expired and batch["expiry_date"] < transaction_date:
            continue
        available = max(0.0, float(batch["remaining_kg"]))
        if available <= 1e-9:
            continue
        allocated = min(available, left)
        plan.append({
            "purchase_id": batch["id"],
            "batch_code": batch["batch_code"],
            "quantity_kg": round(allocated, 6),
            "cost_per_kg": float(batch["cost_per_kg"]),
        })
        left -= allocated
        if left <= 1e-9:
            break
    return plan


def _write_batch_allocations(
    cursor: sqlite3.Cursor,
    transaction_type: str,
    transaction_id: int,
    plan: List[Dict[str, Any]]
) -> None:
    """Persist a previously validated FIFO allocation plan."""
    if transaction_type == "sale":
        table_name, foreign_key = "sale_batch_allocations", "sale_id"
    elif transaction_type == "wastage":
        table_name, foreign_key = "wastage_batch_allocations", "wastage_id"
    else:
        raise ValueError("Unsupported batch allocation type.")

    cursor.executemany(
        f"""INSERT INTO {table_name} ({foreign_key}, purchase_id, quantity_kg)
            VALUES (?, ?, ?)""",
        [(transaction_id, row["purchase_id"], row["quantity_kg"]) for row in plan]
    )


def _backfill_legacy_batch_allocations(cursor: sqlite3.Cursor) -> None:
    """Assign historical Phase 1 sales and wastage entries to batches FIFO."""
    events = []
    cursor.execute("SELECT id, veg_id, sale_date AS entry_date, quantity_kg FROM sales")
    events.extend(("sale", dict(row)) for row in cursor.fetchall())
    cursor.execute("SELECT id, veg_id, record_date AS entry_date, quantity_kg FROM wastage")
    events.extend(("wastage", dict(row)) for row in cursor.fetchall())
    events.sort(key=lambda event: (event[1]["entry_date"], event[1]["id"], event[0]))

    for transaction_type, event in events:
        if transaction_type == "sale":
            table_name, foreign_key = "sale_batch_allocations", "sale_id"
        else:
            table_name, foreign_key = "wastage_batch_allocations", "wastage_id"
        cursor.execute(
            f"SELECT COALESCE(SUM(quantity_kg), 0) FROM {table_name} WHERE {foreign_key} = ?",
            (event["id"],)
        )
        already_allocated = float(cursor.fetchone()[0])
        missing = max(0.0, float(event["quantity_kg"]) - already_allocated)
        if missing <= 1e-9:
            continue

        plan = _fifo_plan(cursor, event["veg_id"], event["entry_date"], missing)
        if plan:
            _write_batch_allocations(cursor, transaction_type, event["id"], plan)
        if transaction_type == "wastage" and plan:
            fifo_cost = round(sum(row["quantity_kg"] * row["cost_per_kg"] for row in plan), 2)
            cursor.execute("UPDATE wastage SET loss_cost = ? WHERE id = ?", (fifo_cost, event["id"]))


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
    if p_date.date() > datetime.now(BUSINESS_TIMEZONE).date():
        raise ValueError("Purchase date cannot be in the future.")
    if not math.isfinite(float(quantity_kg)) or float(quantity_kg) <= 0:
        raise ValueError("Purchase quantity must be a finite number greater than zero.")
    if float(quantity_kg) > 5000:
        raise ValueError("Purchase quantity cannot exceed 5,000 kg.")
    if not math.isfinite(float(cost_per_kg)) or float(cost_per_kg) <= 0:
        raise ValueError("Purchase cost must be a finite number greater than zero.")
    if float(cost_per_kg) > 100000:
        raise ValueError("Purchase cost cannot exceed ₹100,000 per kg.")

    # Calculate expiry date if not provided
    if not expiry_date:
        calc_expiry = p_date + timedelta(days=veg["shelf_life_days"])
        expiry_date = calc_expiry.strftime("%Y-%m-%d")

    # Generate batch code if not provided
    if not batch_code:
        sanitized_name = "".join(c for c in veg["name"] if c.isalnum())[:3].upper()
        time_part = datetime.now(BUSINESS_TIMEZONE).strftime("%H%M%S%f")
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
    """Record a sale atomically and allocate its cost to the oldest batches."""
    quantity_kg = float(quantity_kg)
    selling_price_per_kg = float(selling_price_per_kg)
    sale_day = datetime.strptime(sale_date, "%Y-%m-%d").date()
    if sale_day > datetime.now(BUSINESS_TIMEZONE).date():
        raise ValueError("Sale date cannot be in the future.")
    if not math.isfinite(quantity_kg) or quantity_kg <= 0:
        raise ValueError("Sale quantity must be a finite number greater than zero.")
    if quantity_kg > 5000:
        raise ValueError("Sale quantity cannot exceed 5,000 kg.")
    if not math.isfinite(selling_price_per_kg) or selling_price_per_kg <= 0:
        raise ValueError("Selling price must be a finite number greater than zero.")
    if selling_price_per_kg > 100000:
        raise ValueError("Selling price cannot exceed ₹100,000 per kg.")
    if not get_vegetable_by_id(veg_id):
        raise ValueError(f"Vegetable with ID {veg_id} does not exist.")

    revenue = round(quantity_kg * selling_price_per_kg, 2)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        plan = _fifo_plan(cursor, veg_id, sale_date, quantity_kg, exclude_expired=True)
        allocated_quantity = sum(row["quantity_kg"] for row in plan)
        if allocated_quantity + 1e-6 < quantity_kg:
            current_stock = sum(
                float(batch["remaining_kg"])
                for batch in _remaining_batches(cursor, veg_id, sale_date)
                if batch["expiry_date"] >= sale_date
            )
            raise ValueError(
                f"Insufficient eligible stock. Available: {current_stock:.2f} kg, "
                f"Requested: {quantity_kg:.2f} kg."
            )

        cursor.execute("""
            INSERT INTO sales (veg_id, sale_date, quantity_kg, selling_price_per_kg, revenue)
            VALUES (?, ?, ?, ?, ?)
        """, (veg_id, sale_date, float(quantity_kg), float(selling_price_per_kg), revenue))
        sale_id = cursor.lastrowid
        _write_batch_allocations(cursor, "sale", sale_id, plan)
        conn.commit()
        return sale_id


def get_all_sales() -> List[Dict[str, Any]]:
    """Return sales with FIFO cost of goods sold and gross margin."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, v.name as veg_name, v.unit,
                   ROUND(COALESCE((
                       SELECT SUM(a.quantity_kg * p.cost_per_kg)
                       FROM sale_batch_allocations a
                       JOIN purchases p ON p.id = a.purchase_id
                       WHERE a.sale_id = s.id
                   ), 0), 2) AS cost_of_goods_sold,
                   ROUND(s.revenue - COALESCE((
                       SELECT SUM(a.quantity_kg * p.cost_per_kg)
                       FROM sale_batch_allocations a
                       JOIN purchases p ON p.id = a.purchase_id
                       WHERE a.sale_id = s.id
                   ), 0), 2) AS gross_margin
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
    loss_cost: Optional[float] = None,
    notes: Optional[str] = None
) -> int:
    """
    Record a write-off and value it at the cost of its FIFO source batches.
    ``loss_cost`` remains accepted for compatibility with older callers, but
    transaction cost is always derived from the allocated purchase batches.
    """
    quantity_kg = float(quantity_kg)
    wastage_day = datetime.strptime(record_date, "%Y-%m-%d").date()
    if wastage_day > datetime.now(BUSINESS_TIMEZONE).date():
        raise ValueError("Write-off date cannot be in the future.")
    if not math.isfinite(quantity_kg) or quantity_kg <= 0:
        raise ValueError("Wastage quantity must be a finite number greater than zero.")
    if quantity_kg > 5000:
        raise ValueError("Wastage quantity cannot exceed 5,000 kg.")
    if not reason or not reason.strip():
        raise ValueError("A wastage reason is required.")
    if not get_vegetable_by_id(veg_id):
        raise ValueError(f"Vegetable with ID {veg_id} does not exist.")
    clean_notes = notes.strip() if notes and notes.strip() else None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        plan = _fifo_plan(cursor, veg_id, record_date, quantity_kg)
        allocated_quantity = sum(row["quantity_kg"] for row in plan)
        if allocated_quantity + 1e-6 < quantity_kg:
            current_stock = _live_stock_from_cursor(cursor, veg_id)
            raise ValueError(
                f"Wastage exceeds eligible stock. Available: {current_stock:.2f} kg, "
                f"Requested: {quantity_kg:.2f} kg."
            )
        fifo_loss_cost = round(
            sum(row["quantity_kg"] * row["cost_per_kg"] for row in plan), 2
        )
        cursor.execute("""
            INSERT INTO wastage (veg_id, record_date, quantity_kg, reason, loss_cost, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (veg_id, record_date, quantity_kg, reason.strip(), fifo_loss_cost, clean_notes))
        wastage_id = cursor.lastrowid
        _write_batch_allocations(cursor, "wastage", wastage_id, plan)
        conn.commit()
        return wastage_id


def get_all_wastage() -> List[Dict[str, Any]]:
    """Return write-offs with the value of their consumed FIFO batches."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.*, v.name as veg_name, v.unit,
                   ROUND(COALESCE((
                       SELECT SUM(a.quantity_kg * p.cost_per_kg)
                       FROM wastage_batch_allocations a
                       JOIN purchases p ON p.id = a.purchase_id
                       WHERE a.wastage_id = w.id
                   ), w.loss_cost), 2) AS loss_cost
            FROM wastage w
            JOIN vegetables v ON w.veg_id = v.id
            ORDER BY w.record_date DESC, w.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


# ==========================================
# LIVE STOCK & INVENTORY MATHEMATICAL ENGINE
# ==========================================

def _live_stock_from_cursor(cursor: sqlite3.Cursor, veg_id: int) -> float:
    """Calculate stock from the three ledgers using the conservation identity."""
    totals = []
    for table_name in ("purchases", "sales", "wastage"):
        cursor.execute(
            f"SELECT COALESCE(SUM(quantity_kg), 0.0) FROM {table_name} WHERE veg_id = ?",
            (veg_id,)
        )
        totals.append(float(cursor.fetchone()[0]))
    return max(0.0, round(totals[0] - totals[1] - totals[2], 2))


def get_batch_balances(veg_id: int) -> List[Dict[str, Any]]:
    """Return all inward batches with their remaining quantity and FIFO cost."""
    with get_connection() as conn:
        cursor = conn.cursor()
        rows = _remaining_batches(cursor, veg_id)
        for row in rows:
            row["remaining_kg"] = max(0.0, round(float(row["remaining_kg"]), 2))
            row["purchased_kg"] = round(float(row["purchased_kg"]), 2)
            row["cost_per_kg"] = round(float(row["cost_per_kg"]), 2)
        return rows


def get_recent_transactions(limit: int = 50) -> List[Dict[str, Any]]:
    """Return a unified, newest-first audit ledger for inward and outward stock."""
    limit = max(1, min(int(limit), 500))
    transactions: List[Dict[str, Any]] = []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, 'Purchase' AS type, p.veg_id, v.name AS veg_name,
                   p.purchase_date AS transaction_date, p.quantity_kg,
                   p.cost_per_kg AS unit_price,
                   ROUND(p.quantity_kg * p.cost_per_kg, 2) AS amount,
                   NULL AS reason
            FROM purchases p JOIN vegetables v ON v.id = p.veg_id
            UNION ALL
            SELECT s.id, 'Sale' AS type, s.veg_id, v.name AS veg_name,
                   s.sale_date AS transaction_date, s.quantity_kg,
                   s.selling_price_per_kg AS unit_price, s.revenue AS amount,
                   NULL AS reason
            FROM sales s JOIN vegetables v ON v.id = s.veg_id
            UNION ALL
            SELECT w.id, 'Wastage' AS type, w.veg_id, v.name AS veg_name,
                   w.record_date AS transaction_date, w.quantity_kg,
                   NULL AS unit_price,
                   ROUND(COALESCE((
                       SELECT SUM(a.quantity_kg * p.cost_per_kg)
                       FROM wastage_batch_allocations a
                       JOIN purchases p ON p.id = a.purchase_id
                       WHERE a.wastage_id = w.id
                   ), w.loss_cost), 2) AS amount,
                   w.reason
            FROM wastage w JOIN vegetables v ON v.id = w.veg_id
            ORDER BY transaction_date DESC, id DESC
            LIMIT ?
        """, (limit,))
        for row in cursor.fetchall():
            transactions.append(dict(row))
    return transactions


def get_operations_summary(from_date: str, to_date: str) -> Dict[str, Any]:
    """Aggregate sales, procurement, and FIFO-valued waste over an inclusive range."""
    start = datetime.strptime(from_date, "%Y-%m-%d").date()
    end = datetime.strptime(to_date, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("The report end date must be on or after the start date.")
    if (end - start).days > 366:
        raise ValueError("Choose a report range of 367 days or less.")

    daily: Dict[str, Dict[str, Any]] = {}
    cursor_date = start
    while cursor_date <= end:
        key = cursor_date.isoformat()
        daily[key] = {
            "date": key,
            "sales_revenue": 0.0,
            "sold_kg": 0.0,
            "wastage_cost": 0.0,
            "wasted_kg": 0.0,
            "procurement_cost": 0.0,
            "purchased_kg": 0.0,
        }
        cursor_date += timedelta(days=1)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sale_date AS entry_date, SUM(revenue) AS amount,
                   SUM(quantity_kg) AS quantity
            FROM sales WHERE sale_date BETWEEN ? AND ? GROUP BY sale_date
        """, (from_date, to_date))
        for row in cursor.fetchall():
            day = daily[row["entry_date"]]
            day["sales_revenue"] = round(float(row["amount"]), 2)
            day["sold_kg"] = round(float(row["quantity"]), 2)

        cursor.execute("""
            SELECT w.record_date AS entry_date, SUM(w.quantity_kg) AS quantity,
                   SUM(COALESCE((
                       SELECT SUM(a.quantity_kg * p.cost_per_kg)
                       FROM wastage_batch_allocations a
                       JOIN purchases p ON p.id = a.purchase_id
                       WHERE a.wastage_id = w.id
                   ), w.loss_cost)) AS amount
            FROM wastage w WHERE w.record_date BETWEEN ? AND ?
            GROUP BY w.record_date
        """, (from_date, to_date))
        for row in cursor.fetchall():
            day = daily[row["entry_date"]]
            day["wastage_cost"] = round(float(row["amount"]), 2)
            day["wasted_kg"] = round(float(row["quantity"]), 2)

        cursor.execute("""
            SELECT purchase_date AS entry_date,
                   SUM(quantity_kg * cost_per_kg) AS amount,
                   SUM(quantity_kg) AS quantity
            FROM purchases WHERE purchase_date BETWEEN ? AND ?
            GROUP BY purchase_date
        """, (from_date, to_date))
        for row in cursor.fetchall():
            day = daily[row["entry_date"]]
            day["procurement_cost"] = round(float(row["amount"]), 2)
            day["purchased_kg"] = round(float(row["quantity"]), 2)

    daily_rows = list(daily.values())
    return {
        "from_date": from_date,
        "to_date": to_date,
        "sales_revenue": round(sum(row["sales_revenue"] for row in daily_rows), 2),
        "sold_kg": round(sum(row["sold_kg"] for row in daily_rows), 2),
        "wastage_cost": round(sum(row["wastage_cost"] for row in daily_rows), 2),
        "wasted_kg": round(sum(row["wasted_kg"] for row in daily_rows), 2),
        "procurement_cost": round(sum(row["procurement_cost"] for row in daily_rows), 2),
        "purchased_kg": round(sum(row["purchased_kg"] for row in daily_rows), 2),
        "daily": daily_rows,
    }


def calculate_live_stock(veg_id: int) -> float:
    """
    Computes real-time available stock using the fundamental balance equation:
    Current Stock = Total Purchased - Total Sold - Total Wasted
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        return _live_stock_from_cursor(cursor, veg_id)


def get_stock_overview() -> List[Dict[str, Any]]:
    """
    Produces a comprehensive inventory health summary for all vegetables.
    Calculates current stock, total inward, total outward, nearest expiry date,
    days remaining, and status indicators.
    """
    vegetables = get_all_vegetables()
    overview = []
    today = datetime.now(BUSINESS_TIMEZONE).date()

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

            # Ignore fully depleted batches when finding the next expiry.
            active_batches = [
                batch for batch in _remaining_batches(cursor, vid)
                if float(batch["remaining_kg"]) > 1e-6
            ]
            available_for_sale = round(sum(
                float(batch["remaining_kg"])
                for batch in active_batches
                if batch["expiry_date"] >= today.isoformat()
            ), 2)
            saleable_batches = [
                batch for batch in active_batches
                if batch["expiry_date"] >= today.isoformat()
            ]
            expiry_candidates = saleable_batches or active_batches
            next_batch = min(
                expiry_candidates,
                key=lambda batch: (batch["expiry_date"], batch["purchase_date"], batch["id"]),
                default=None
            )
            nearest_expiry = next_batch["expiry_date"] if next_batch else "N/A"
            days_to_expiry = None

            if next_batch:
                exp_date = datetime.strptime(next_batch["expiry_date"], "%Y-%m-%d").date()
                days_to_expiry = (exp_date - today).days

            # Determine Health Status
            if current_stock == 0.0:
                status = "OUT OF STOCK"
                status_color = "red"
            elif current_stock > 0 and available_for_sale <= 0:
                status = "EXPIRED BATCH"
                status_color = "red"
            elif days_to_expiry is not None and 0 <= days_to_expiry <= 1:
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
                "available_for_sale_kg": available_for_sale,
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
        cursor.execute("DROP TABLE IF EXISTS sale_batch_allocations")
        cursor.execute("DROP TABLE IF EXISTS wastage_batch_allocations")
        cursor.execute("DROP TABLE IF EXISTS wastage")
        cursor.execute("DROP TABLE IF EXISTS sales")
        cursor.execute("DROP TABLE IF EXISTS purchases")
        cursor.execute("DROP TABLE IF EXISTS vegetables")
        conn.commit()
    init_db()
