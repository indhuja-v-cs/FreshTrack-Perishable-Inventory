"""
app.py - Main Streamlit Application
-----------------------------------
Perishable Vegetable Inventory & Wastage Reduction System (Phase 1: 40% Milestone)
Features:
- Live Inventory & Expiry Monitor with Batch Inspection
- Inward Stock / Procurement Management with dynamic shelf-life calculation
- Smart Perishable Restock Recommendations Engine
- Vegetable Master Catalog Management
- Interactive Mathematical Verification & Roadmap
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import database as db
import seed_data
import recommendation as rec

# Set Streamlit page configuration
st.set_page_config(
    page_title="FreshTrack - Perishable Inventory System",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Ensure database tables exist
db.init_db()

# Custom Styling for polished UI
st.markdown("""
<style>
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.title("🌱 FreshTrack")
    st.caption("Perishable Vegetable Inventory System")
    st.markdown("---")
    
    st.markdown("### 📌 Milestone Status")
    st.success("✔ **Phase 1: Foundation (40% Complete)**")
    st.info("⏳ Phase 2: Operations & POS Logging")
    st.info("⏳ Phase 3: Advanced ML Forecasting")
    st.markdown("---")

    st.markdown("### ⚙️ Database Utilities")
    vegetables_list = db.get_all_vegetables()
    st.write(f"**Tracked Commodities:** {len(vegetables_list)} items")
    st.write(f"**Database Engine:** SQLite (Local & Offline)")
    
    if st.button("🔄 Reset & Load Sample Data", help="Reloads initial realistic perishable inventory dataset"):
        seed_data.seed_database(reset=True)
        st.success("Sample database reloaded!")
        st.rerun()

    st.markdown("---")
    st.caption("FreshTrack • Academic Demonstration System")


# ==========================================
# MAIN HEADER
# ==========================================
st.title("🥦 FreshTrack: Perishable Inventory & Wastage System")
st.markdown(
    "A self-contained inventory management engine specialized for perishable agricultural commodities. "
    "Features shelf-life batch tracking, FIFO expiry alerts, real-time stock balance, and spoilage-aware reorder recommendations."
)

# If database has no vegetables yet, offer quick seeding
if not vegetables_list:
    st.warning("⚠️ No vegetables found in the database. Click the button below to initialize with sample perishables.")
    if st.button("🚀 Initialize Sample Inventory"):
        seed_data.seed_database(reset=True)
        st.rerun()
    st.stop()


# ==========================================
# TABS NAVIGATION
# ==========================================
tab_overview, tab_procurement, tab_rec, tab_catalog, tab_roadmap = st.tabs([
    "📊 Live Inventory & Expiry Monitor",
    "📦 Inward Stock (Procurement)",
    "💡 Reorder Recommendations",
    "🥗 Vegetable Master Catalog",
    "🎯 Milestone Architecture & Logic"
])


# ==============================================================================
# TAB 1: LIVE INVENTORY & EXPIRY MONITOR
# ==============================================================================
with tab_overview:
    st.subheader("Live Stock Overview & Perishable Health Status")
    
    overview = db.get_stock_overview()
    df_overview = pd.DataFrame(overview)
    
    if not df_overview.empty:
        # Summary Metrics
        total_stock = df_overview["current_stock_kg"].sum()
        total_items = len(df_overview)
        low_stock_count = len(df_overview[df_overview["status"] == "LOW STOCK"])
        expiring_soon_count = len(df_overview[df_overview["status"].isin(["EXPIRING SOON", "EXPIRED BATCH"])])
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📦 Total Active Stock", f"{total_stock:.1f} kg")
        col2.metric("🏷️ Tracked Vegetables", f"{total_items}")
        col3.metric("⚠️ Low Stock Alerts", f"{low_stock_count}", delta_color="inverse")
        col4.metric("⏰ Expiring Within 24-48h", f"{expiring_soon_count}", delta_color="inverse")
        
        st.markdown("---")
        
        # Filters
        f_col1, f_col2 = st.columns([2, 2])
        with f_col1:
            categories = ["All"] + sorted(list(df_overview["category"].unique()))
            selected_category = st.selectbox("Filter by Category", categories)
        with f_col2:
            statuses = ["All"] + sorted(list(df_overview["status"].unique()))
            selected_status = st.selectbox("Filter by Stock Status", statuses)
            
        filtered_df = df_overview.copy()
        if selected_category != "All":
            filtered_df = filtered_df[filtered_df["category"] == selected_category]
        if selected_status != "All":
            filtered_df = filtered_df[filtered_df["status"] == selected_status]
            
        display_cols = [
            "name", "category", "current_stock_kg", "unit", 
            "reorder_threshold_kg", "nearest_expiry", "days_to_expiry", "status"
        ]
        
        renamed_df = filtered_df[display_cols].rename(columns={
            "name": "Vegetable Name",
            "category": "Category",
            "current_stock_kg": "Current Stock (kg)",
            "unit": "Unit",
            "reorder_threshold_kg": "Reorder Threshold (kg)",
            "nearest_expiry": "Nearest Batch Expiry",
            "days_to_expiry": "Days Remaining",
            "status": "Stock Status"
        })
        
        st.dataframe(
            renamed_df,
            use_container_width=True,
            hide_index=True
        )
        
        # Actionable Shelf-Life Alerts
        expiring_items = df_overview[df_overview["status"].isin(["EXPIRING SOON", "EXPIRED BATCH"])]
        if not expiring_items.empty:
            st.markdown("### 🚨 Urgent Perishable Alerts")
            for _, row in expiring_items.iterrows():
                if row["days_to_expiry"] is not None and row["days_to_expiry"] <= 1:
                    st.error(
                        f"⚠️ **{row['name']}** has **{row['current_stock_kg']} kg** expiring on **{row['nearest_expiry']}** "
                        f"({row['days_to_expiry']} days left). Recommended immediate markdown or priority FIFO sales."
                    )
                    
        # Batch Inspection
        st.markdown("---")
        st.subheader("🔍 Inspect Inward Batches by Vegetable")
        selected_veg_name = st.selectbox("Select Vegetable to View Batches", df_overview["name"].tolist())
        selected_veg_id = df_overview[df_overview["name"] == selected_veg_name]["id"].values[0]
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT batch_code, purchase_date, quantity_kg, cost_per_kg, expiry_date
                FROM purchases
                WHERE veg_id = ?
                ORDER BY purchase_date DESC
            """, (int(selected_veg_id),))
            batches = [dict(r) for r in cursor.fetchall()]
            
        if batches:
            df_batches = pd.DataFrame(batches).rename(columns={
                "batch_code": "Batch Code",
                "purchase_date": "Purchase Date",
                "quantity_kg": "Purchased Qty (kg)",
                "cost_per_kg": "Cost / kg (₹)",
                "expiry_date": "Batch Expiry Date"
            })
            st.dataframe(df_batches, use_container_width=True, hide_index=True)
        else:
            st.info(f"No procurement batches logged for {selected_veg_name} yet.")


# ==============================================================================
# TAB 2: INWARD STOCK (PROCUREMENT)
# ==============================================================================
with tab_procurement:
    st.subheader("Record Inward Procurement / New Stock Batch")
    st.markdown("Log incoming farm/mandi shipments. Expiry date is auto-calculated using the item's biological shelf-life.")
    
    veg_options = {v["name"]: v for v in vegetables_list}
    col_form, col_history = st.columns([1, 1])
    
    with col_form:
        with st.form("procurement_form", clear_on_submit=True):
            chosen_veg_name = st.selectbox("Select Vegetable", list(veg_options.keys()))
            chosen_veg = veg_options[chosen_veg_name]
            
            st.info(f"🌿 **{chosen_veg_name}** | Shelf Life: **{chosen_veg['shelf_life_days']} days** | Recommended Temp: **{chosen_veg['optimal_temp_celsius']}°C**")
            
            p_date = st.date_input("Arrival / Purchase Date", datetime.now().date())
            qty = st.number_input("Quantity Received (kg)", min_value=0.5, max_value=5000.0, value=20.0, step=1.0)
            cost = st.number_input("Procurement Cost per kg (₹)", min_value=1.0, max_value=500.0, value=25.0, step=1.0)
            
            calculated_expiry = p_date + timedelta(days=chosen_veg["shelf_life_days"])
            st.markdown(f"**Calculated Batch Expiry Date:** `{calculated_expiry.strftime('%Y-%m-%d')}`")
            
            custom_batch = st.text_input("Custom Batch Code (Optional)", placeholder="Leave blank to auto-generate")
            submit_purchase = st.form_submit_button("📥 Inward Stock & Update Inventory")
            
            if submit_purchase:
                try:
                    batch_id = db.record_purchase(
                        veg_id=chosen_veg["id"],
                        purchase_date=p_date.strftime("%Y-%m-%d"),
                        quantity_kg=qty,
                        cost_per_kg=cost,
                        batch_code=custom_batch if custom_batch.strip() else None,
                        expiry_date=calculated_expiry.strftime("%Y-%m-%d")
                    )
                    st.success(f"✅ Inward batch successfully registered! Batch ID #{batch_id}. Live stock updated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error logging inward batch: {e}")
                    
    with col_history:
        st.markdown("### 📋 Recent Procurement History")
        purchases = db.get_all_purchases()
        if purchases:
            df_p = pd.DataFrame(purchases)[["veg_name", "batch_code", "purchase_date", "quantity_kg", "cost_per_kg", "expiry_date"]]
            df_p = df_p.rename(columns={
                "veg_name": "Vegetable",
                "batch_code": "Batch Code",
                "purchase_date": "Date",
                "quantity_kg": "Qty (kg)",
                "cost_per_kg": "Cost/kg (₹)",
                "expiry_date": "Expiry Date"
            })
            st.dataframe(df_p.head(10), use_container_width=True, hide_index=True)
        else:
            st.info("No purchase records found.")


# ==============================================================================
# TAB 3: SMART REORDER RECOMMENDATIONS
# ==============================================================================
with tab_rec:
    st.subheader("💡 Spoilage-Aware Reorder Recommendations")
    st.markdown(
        "Standard inventory formulas (like Wilson EOQ) fail for perishables because ordering too much leads to 100% spoilage. "
        "Our recommendation engine dynamically caps restock volumes to what can realistically be sold before the biological shelf life expires."
    )
    
    recommendations = rec.get_all_recommendations()
    df_rec = pd.DataFrame(recommendations)
    
    if not df_rec.empty:
        # Display Table
        rec_display = df_rec[[
            "name", "current_stock_kg", "avg_daily_demand_kg", "shelf_life_days",
            "perishable_holding_cap_kg", "recommended_order_kg", "urgency"
        ]].rename(columns={
            "name": "Vegetable",
            "current_stock_kg": "Current Stock (kg)",
            "avg_daily_demand_kg": "Daily Demand (kg/day)",
            "shelf_life_days": "Shelf Life (Days)",
            "perishable_holding_cap_kg": "Max Safe Cap (kg)",
            "recommended_order_kg": "Recommended Reorder (kg)",
            "urgency": "Restock Urgency"
        })
        
        st.dataframe(rec_display, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("🧠 Per-Commodity Decision Breakdown")
        
        selected_veg_rec = st.selectbox("Select Vegetable for Detailed Explanation", df_rec["name"].tolist())
        detail = df_rec[df_rec["name"] == selected_veg_rec].iloc[0]
        
        col_d1, col_d2 = st.columns([1, 1])
        with col_d1:
            st.markdown(f"#### **{detail['name']}** Analysis")
            st.write(f"- **Current Stock:** `{detail['current_stock_kg']} kg`")
            st.write(f"- **Observed Daily Sales:** `{detail['avg_daily_demand_kg']} kg/day`")
            st.write(f"- **Biological Shelf Life:** `{detail['shelf_life_days']} days`")
            st.write(f"- **Historical Wastage Rate:** `{detail['wastage_rate_pct']}%`")
            st.write(f"- **Maximum Safe Holding Cap:** `{detail['perishable_holding_cap_kg']} kg`")
            st.write(f"- **Recommended Restock Quantity:** `{detail['recommended_order_kg']} kg`")
            
        with col_d2:
            st.info(f"**Decision Status:** `{detail['urgency']}`\n\n**Reasoning:** {detail['reasoning']}")
            st.caption(
                "💡 **Perishable Rule:** Even if supplier offers a bulk discount, the system never recommends "
                "ordering more than the Max Safe Cap to prevent guaranteed spoilage."
            )


# ==============================================================================
# TAB 4: VEGETABLE MASTER CATALOG
# ==============================================================================
with tab_catalog:
    st.subheader("Vegetable Master Catalog")
    st.markdown("Define agricultural commodities, expected shelf-life, and reorder thresholds.")
    
    cat_col1, cat_col2 = st.columns([1, 1])
    
    with cat_col1:
        st.markdown("### ➕ Register New Vegetable")
        with st.form("new_veg_form", clear_on_submit=True):
            new_name = st.text_input("Vegetable Name", placeholder="e.g., Bitter Gourd (Karela)")
            new_category = st.selectbox("Category", [
                "Leafy Greens", "Fruit Vegetable", "Root Vegetable", 
                "Cruciferous", "Tubers", "Root & Bulb", "Herbs", "Other"
            ])
            new_unit = st.selectbox("Measurement Unit", ["kg", "bunch", "pack"])
            new_shelf_life = st.number_input("Average Shelf Life (Days)", min_value=1, max_value=180, value=5)
            new_threshold = st.number_input("Minimum Reorder Threshold (kg)", min_value=1.0, max_value=500.0, value=15.0)
            new_temp = st.number_input("Optimal Storage Temp (°C)", min_value=-5.0, max_value=35.0, value=8.0)
            
            save_veg = st.form_submit_button("💾 Save Vegetable to Catalog")
            
            if save_veg:
                if not new_name.strip():
                    st.error("Please provide a valid vegetable name.")
                else:
                    try:
                        vid = db.add_vegetable(
                            name=new_name.strip(),
                            category=new_category,
                            unit=new_unit,
                            shelf_life_days=int(new_shelf_life),
                            reorder_threshold_kg=float(new_threshold),
                            optimal_temp_celsius=float(new_temp)
                        )
                        st.success(f"✅ Vegetable '{new_name}' added successfully with ID #{vid}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add vegetable: {e}")
                        
    with cat_col2:
        st.markdown("### 📚 Registered Commodities Catalog")
        all_veg = db.get_all_vegetables()
        if all_veg:
            df_veg = pd.DataFrame(all_veg)[["id", "name", "category", "unit", "shelf_life_days", "reorder_threshold_kg", "optimal_temp_celsius"]]
            df_veg = df_veg.rename(columns={
                "id": "ID",
                "name": "Commodity Name",
                "category": "Category",
                "unit": "Unit",
                "shelf_life_days": "Shelf Life (Days)",
                "reorder_threshold_kg": "Threshold (kg)",
                "optimal_temp_celsius": "Storage Temp (°C)"
            })
            st.dataframe(df_veg, use_container_width=True, hide_index=True)
        else:
            st.info("No vegetables registered in catalog.")


# ==============================================================================
# TAB 5: MILESTONE ARCHITECTURE & LOGIC
# ==============================================================================
with tab_roadmap:
    st.subheader("🎯 Project Architecture & 40% Milestone Status")
    
    st.markdown("""
    ### 1. Milestone Progress Breakdown
    This project is being built in structured phases to ensure mathematical accuracy, robustness, and academic review readiness.
    """)
    
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        st.success("#### 🟢 Phase 1: Foundation (40% Complete)")
        st.markdown("""
        - [x] Relational SQLite Schema with foreign keys
        - [x] Mathematical live stock computation engine
        - [x] Inward procurement batch manager
        - [x] Dynamic batch expiry calculation based on shelf life
        - [x] Real-time health status matrix (Healthy / Low Stock / Expiring)
        - [x] Spoilage-aware reorder recommendation baseline
        - [x] Realistic sample perishable data seeder
        - [x] Master commodity catalog CRUD
        """)
        
    with col_p2:
        st.info("#### 🟡 Phase 2: Operations (Next 30%)")
        st.markdown("""
        - [ ] Daily POS Sales recording terminal
        - [ ] Spoilage / Wastage write-off interface
        - [ ] Wastage reason classification (rotting, damage, pest)
        - [ ] Real-time financial loss valuation ledger
        - [ ] FIFO batch depletion logic
        """)
        
    with col_p3:
        st.info("#### 🔵 Phase 3: AI & Analytics (Final 30%)")
        st.markdown("""
        - [ ] Time-series demand forecasting (Exponential Smoothing / ARIMA)
        - [ ] Dynamic Markdown Pricing engine for expiring stock
        - [ ] Interactive spoilage trend dashboards & heatmaps
        - [ ] Supplier quality rating based on wastage %
        - [ ] Exportable audit reports (CSV/PDF)
        """)
        
    st.markdown("---")
    
    st.markdown("### 2. Mathematical Stock Balance Formula")
    st.latex(r"\text{Current Stock} = \sum(\text{Purchased Quantity}) - \sum(\text{Sold Quantity}) - \sum(\text{Wasted Quantity})")
    
    st.markdown("### 3. Interactive Formula Demonstration")
    st.caption("Test how the database ensures strict inventory balance without arbitrary counters:")
    
    test_c1, test_c2, test_c3 = st.columns(3)
    with test_c1:
        test_inward = st.number_input("Sample Inward Procurement (kg)", value=100.0, step=5.0)
    with test_c2:
        test_sales = st.number_input("Sample Customer Sales (kg)", value=65.0, step=5.0)
    with test_c3:
        test_spoilage = st.number_input("Sample Unsold Spoilage (kg)", value=5.0, step=1.0)
        
    calc_stock = max(0.0, test_inward - test_sales - test_spoilage)
    st.metric("Computed Available Balance", f"{calc_stock:.2f} kg", f"{'Balanced' if calc_stock >= 0 else 'Negative'}")
