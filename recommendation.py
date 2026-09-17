"""
recommendation.py - Perishable Reorder & Wastage Prevention Module
------------------------------------------------------------------
Computes smart restock recommendations based on historical sales velocity,
shelf-life decay constraints, and safety stock thresholds.
"""

from typing import List, Dict, Any
import database as db


def compute_reorder_recommendation(veg_id: int) -> Dict[str, Any]:
    """
    Computes reorder quantity and spoilage risk for a specific vegetable.
    
    Formula:
    1. Average Daily Sales = Total Sales Quantity / Days Observed (default 7 days)
    2. Target Safe Stock = (Daily Sales * Lead Time Days) + Safety Stock Threshold
    3. Maximum Perishable Limit = Shelf Life Days * Daily Sales * (1 - Wastage Ratio)
    4. Recommended Order = clamp(Target Safe Stock - Current Stock, 0, Maximum Perishable Limit)
    """
    veg = db.get_vegetable_by_id(veg_id)
    if not veg:
        raise ValueError(f"Vegetable with ID {veg_id} not found.")

    current_stock = db.calculate_live_stock(veg_id)
    shelf_life = veg["shelf_life_days"]
    reorder_threshold = veg["reorder_threshold_kg"]

    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Total Sales
        cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM sales WHERE veg_id = ?", (veg_id,))
        total_sales = cursor.fetchone()["total"]

        # Total Wastage
        cursor.execute("SELECT COALESCE(SUM(quantity_kg), 0.0) as total FROM wastage WHERE veg_id = ?", (veg_id,))
        total_wastage = cursor.fetchone()["total"]

    # Observed velocity over sample window (assumed 7 days active)
    observed_days = 7
    avg_daily_demand = max(1.0, round(total_sales / observed_days, 2)) if total_sales > 0 else 5.0
    
    # Wastage ratio
    total_movement = total_sales + total_wastage
    wastage_rate = (total_wastage / total_movement) if total_movement > 0 else 0.05

    # Safe stocking window (lead time = 2 days to restock)
    lead_time_days = 2
    safety_buffer = reorder_threshold * 0.5
    target_inventory = (avg_daily_demand * lead_time_days) + safety_buffer

    # Perishable Cap: Never order more than can be sold within the shelf-life window
    perishable_max_holding = max(avg_daily_demand, shelf_life * avg_daily_demand * (1.0 - wastage_rate))

    # Raw deficit
    net_deficit = target_inventory - current_stock
    
    if net_deficit <= 0:
        recommended_order = 0.0
        urgency = "NO RESTOCK NEEDED"
        reasoning = f"Current stock ({current_stock:.1f} kg) is sufficient to cover lead-time demand."
    else:
        # Cap by perishable ceiling to prevent guaranteed spoilage
        recommended_order = min(net_deficit, perishable_max_holding)
        recommended_order = round(max(0.0, recommended_order), 1)
        
        if current_stock == 0:
            urgency = "CRITICAL (STOCKOUT)"
            reasoning = f"Stock is depleted! Need {recommended_order:.1f} kg to satisfy immediate demand without exceeding {shelf_life}-day shelf life."
        elif current_stock <= reorder_threshold:
            urgency = "HIGH (BELOW THRESHOLD)"
            reasoning = f"Stock ({current_stock:.1f} kg) has fallen below safe threshold ({reorder_threshold:.1f} kg)."
        else:
            urgency = "NORMAL"
            reasoning = f"Routine restock of {recommended_order:.1f} kg to maintain optimal inventory buffer."

    return {
        "veg_id": veg_id,
        "name": veg["name"],
        "shelf_life_days": shelf_life,
        "current_stock_kg": current_stock,
        "reorder_threshold_kg": reorder_threshold,
        "avg_daily_demand_kg": avg_daily_demand,
        "wastage_rate_pct": round(wastage_rate * 100, 1),
        "perishable_holding_cap_kg": round(perishable_max_holding, 1),
        "recommended_order_kg": recommended_order,
        "urgency": urgency,
        "reasoning": reasoning
    }


def get_all_recommendations() -> List[Dict[str, Any]]:
    """Returns reorder recommendations for all registered vegetables."""
    vegetables = db.get_all_vegetables()
    return [compute_reorder_recommendation(v["id"]) for v in vegetables]


if __name__ == "__main__":
    db.init_db()
    print("--- Perishable Restock Recommendations Engine ---")
    recs = get_all_recommendations()
    for r in recs:
        print(f"[{r['urgency']}] {r['name']}: Recommend Order {r['recommended_order_kg']} kg | Current: {r['current_stock_kg']} kg | Cap: {r['perishable_holding_cap_kg']} kg")
