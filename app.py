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
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
BUSINESS_TIMEZONE = ZoneInfo("Asia/Kolkata")
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
    st.success("✔ **Phase 1: Foundation (40%)**")
    st.success("✔ **Phase 2: Operations (30%)**")
    st.info("⏳ **Cumulative progress: 75%**")
    st.caption("Forecasting and advanced analytics remain in Phase 3.")
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
    "Phase 2 adds FIFO point-of-sale recording, spoilage write-offs, and purchase-cost-based loss accounting."
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
tab_overview, tab_procurement, tab_operations, tab_rec, tab_catalog, tab_report, tab_roadmap = st.tabs([
    "📊 Live Inventory & Expiry Monitor",
    "📦 Inward Stock (Procurement)",
    "🧾 Sales & Write-offs",
    "💡 Reorder Recommendations",
    "🥗 Vegetable Master Catalog",
    "📈 Operations Report",
    "🎯 Milestone Architecture & Logic",
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
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("📦 Total on Hand", f"{total_stock:.1f} kg")
        col2.metric("🏷️ Tracked Vegetables", f"{total_items}")
        col3.metric("⚠️ Low Stock Alerts", f"{low_stock_count}", delta_color="inverse")
        col4.metric("⏰ Expiring / Expired", f"{expiring_soon_count}", delta_color="inverse")
        today = datetime.now(BUSINESS_TIMEZONE).date().strftime("%Y-%m-%d")
        today_sales = sum(
            row["revenue"] for row in db.get_all_sales() if row["sale_date"] == today
        )
        today_waste = sum(
            row["loss_cost"] for row in db.get_all_wastage() if row["record_date"] == today
        )
        col5.metric("💰 Sales Today", f"₹{today_sales:,.2f}")
        col6.metric("🗑️ Loss Today", f"₹{today_waste:,.2f}", delta_color="inverse")
        
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
            "name", "category", "current_stock_kg", "available_for_sale_kg", "unit",
            "reorder_threshold_kg", "nearest_expiry", "days_to_expiry", "status"
        ]
        
        renamed_df = filtered_df[display_cols].rename(columns={
            "name": "Vegetable Name",
            "category": "Category",
            "current_stock_kg": "Current Stock (kg)",
            "available_for_sale_kg": "Available for Sale (kg)",
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
        
        batches = db.get_batch_balances(int(selected_veg_id))
            
        if batches:
            df_batches = pd.DataFrame(batches)[[
                "batch_code", "purchase_date", "purchased_kg", "remaining_kg",
                "cost_per_kg", "expiry_date"
            ]].rename(columns={
                "batch_code": "Batch Code",
                "purchase_date": "Purchase Date",
                "purchased_kg": "Purchased Qty (kg)",
                "remaining_kg": "Remaining Qty (kg)",
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
            
            p_date = st.date_input("Arrival / Purchase Date", datetime.now(BUSINESS_TIMEZONE).date())
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
# TAB 3: POINT OF SALE AND WASTAGE WRITE-OFFS
# ==============================================================================
with tab_operations:
    st.subheader("Daily Operations")
    st.markdown(
        "Log sales and spoilage as transactions. Sales and write-offs consume the oldest "
        "available inward batches first; loss value is calculated from those batches' purchase costs."
    )

    current_inventory = db.get_stock_overview()
    sale_options = {
        row["name"]: row for row in current_inventory
        if row["available_for_sale_kg"] > 0
    }
    waste_options = {
        row["name"]: row for row in current_inventory
        if row["current_stock_kg"] > 0
    }
    sale_col, waste_col = st.columns(2)

    with sale_col:
        st.markdown("### Record a Sale")
        if not sale_options:
            st.info("No stock is available to sell. Record an inward batch first.")
        else:
            with st.form("pos_sale_form", clear_on_submit=True):
                sale_name = st.selectbox("Vegetable sold", list(sale_options.keys()))
                sale_veg = sale_options[sale_name]
                st.caption(
                    f"Available to sell: {sale_veg['available_for_sale_kg']:.2f} "
                    f"{sale_veg['unit']} · FIFO cost uses the oldest remaining batch."
                )
                sale_date = st.date_input("Sale date", datetime.now(BUSINESS_TIMEZONE).date(), key="sale_date")
                sale_qty = st.number_input(
                    f"Quantity sold ({sale_veg['unit']})",
                    min_value=0.1, max_value=5000.0, value=1.0, step=0.5,
                    key="sale_quantity"
                )
                sale_price = st.number_input(
                    "Selling price per kg (₹)",
                    min_value=0.01, max_value=100000.0, value=35.0, step=1.0,
                    key="sale_price"
                )
                submit_sale = st.form_submit_button("Record sale")

                if submit_sale:
                    try:
                        sale_id = db.record_sale(
                            veg_id=int(sale_veg["id"]),
                            sale_date=sale_date.strftime("%Y-%m-%d"),
                            quantity_kg=sale_qty,
                            selling_price_per_kg=sale_price
                        )
                        sale_record = next(
                            row for row in db.get_all_sales() if row["id"] == sale_id
                        )
                        st.success(
                            f"Sale #{sale_id} recorded · Revenue ₹{sale_record['revenue']:,.2f} · "
                            f"FIFO cost ₹{sale_record['cost_of_goods_sold']:,.2f} · "
                            f"Gross margin ₹{sale_record['gross_margin']:,.2f}"
                        )
                    except (ValueError, sqlite3.Error) as error:
                        st.error(f"Sale not recorded: {error}")

    with waste_col:
        st.markdown("### Record Spoilage / Wastage")
        if not waste_options:
            st.info("No stock is available to write off.")
        else:
            with st.form("wastage_form", clear_on_submit=True):
                waste_name = st.selectbox("Vegetable written off", list(waste_options.keys()))
                waste_veg = waste_options[waste_name]
                st.caption(
                    f"Available to write off: {waste_veg['current_stock_kg']:.2f} "
                    f"{waste_veg['unit']} · FIFO purchase cost will be used for the loss value."
                )
                waste_date = st.date_input("Write-off date", datetime.now(BUSINESS_TIMEZONE).date(), key="waste_date")
                waste_qty = st.number_input(
                    f"Quantity wasted ({waste_veg['unit']})",
                    min_value=0.1, max_value=5000.0, value=1.0, step=0.5,
                    key="waste_quantity"
                )
                waste_reason = st.selectbox("Reason", [
                    "Rotting", "Overripe", "Transit damage", "Fungal spots",
                    "Unsold", "Pest damage", "Other"
                ])
                waste_notes = st.text_input(
                    "Notes (optional)",
                    placeholder="Add a short detail for the audit ledger"
                )
                submit_waste = st.form_submit_button("Record write-off")

                if submit_waste:
                    try:
                        wastage_id = db.record_wastage(
                            veg_id=int(waste_veg["id"]),
                            record_date=waste_date.strftime("%Y-%m-%d"),
                            quantity_kg=waste_qty,
                            reason=waste_reason,
                            notes=waste_notes
                        )
                        waste_record = next(
                            row for row in db.get_all_wastage()
                            if row["id"] == wastage_id
                        )
                        st.success(
                            f"Write-off #{wastage_id} recorded · "
                            f"FIFO loss cost ₹{waste_record['loss_cost']:,.2f}"
                        )
                    except (ValueError, sqlite3.Error) as error:
                        st.error(f"Write-off not recorded: {error}")


# ==============================================================================
# TAB 4: SMART REORDER RECOMMENDATIONS
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
# TAB 5: VEGETABLE MASTER CATALOG
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
# TAB 6: OPERATIONS REPORT
# ==============================================================================
with tab_report:
    st.subheader("Sales, Procurement & Spoilage Summary")
    today = datetime.now(BUSINESS_TIMEZONE).date()
    date_range = st.date_input(
        "Reporting period",
        value=(today - timedelta(days=29), today),
        key="operations_report_range"
    )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        report_start, report_end = date_range
        if report_start and report_end:
            try:
                report = db.get_operations_summary(
                    report_start.strftime("%Y-%m-%d"),
                    report_end.strftime("%Y-%m-%d")
                )
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Sales revenue", f"₹{report['sales_revenue']:,.2f}")
                m2.metric("FIFO-valued wastage", f"₹{report['wastage_cost']:,.2f}")
                m3.metric("Procurement cost", f"₹{report['procurement_cost']:,.2f}")
                m4.metric(
                    "Outward quantity",
                    f"{report['sold_kg'] + report['wasted_kg']:,.2f} kg",
                    help=f"{report['sold_kg']:,.2f} kg sold · {report['wasted_kg']:,.2f} kg written off"
                )

                st.markdown("### Daily cash-flow and loss values")
                df_daily = pd.DataFrame(report["daily"])
                if not df_daily.empty:
                    st.bar_chart(
                        df_daily.set_index("date")[[
                            "sales_revenue", "wastage_cost", "procurement_cost"
                        ]],
                        y_label="Amount (₹)"
                    )

                st.markdown("### Recent transaction ledger")
                ledger_rows = db.get_recent_transactions(limit=100)
                if ledger_rows:
                    ledger = pd.DataFrame(ledger_rows).rename(columns={
                        "type": "Type",
                        "veg_name": "Vegetable",
                        "transaction_date": "Date",
                        "quantity_kg": "Quantity (kg)",
                        "unit_price": "Unit price (₹)",
                        "amount": "Amount (₹)",
                        "reason": "Reason",
                    })
                    st.dataframe(
                        ledger[[
                            "Type", "Vegetable", "Date", "Quantity (kg)",
                            "Unit price (₹)", "Amount (₹)", "Reason"
                        ]],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No purchase, sale, or write-off transactions have been recorded.")
            except ValueError as error:
                st.error(f"Could not generate the report: {error}")
    else:
        st.caption("Choose a start date and an end date to generate the report.")


# ==============================================================================
# TAB 7: MILESTONE ARCHITECTURE & LOGIC
# ==============================================================================
with tab_roadmap:
    st.subheader("🎯 Project Architecture & 75% Progress Status")
    
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
        st.success("#### 🟢 Phase 2: Operations (30% Complete)")
        st.markdown("""
        - [x] Daily POS sales entry and stock validation
        - [x] Spoilage / wastage write-off interface
        - [x] Wastage reason and optional note capture
        - [x] Purchase-cost-based loss valuation
        - [x] FIFO batch depletion with auditable allocations
        - [x] Operations totals and date-range report
        """)
        
    with col_p3:
        st.info("#### 🔵 Phase 3: Analytics & Forecasting (25% Remaining)")
        st.markdown("""
        - [x] Basic sales, procurement, and spoilage summaries (5% foundation)
        - [ ] Demand forecasting after sufficient sales history is available
        - [ ] Perishable decay penalties and suggested restock quantities
        - [ ] Supplier quality analysis and advanced trend views
        - [ ] Exportable audit reports
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
