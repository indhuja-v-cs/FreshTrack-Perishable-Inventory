# 🌱 FreshTrack: Perishable Vegetable Inventory & Wastage Reduction System

A local, lightweight, and self-contained inventory management application specifically designed for perishable agricultural commodities (vegetables, greens, roots, and tubers). It tracks inward procurement batches, computes real-time stock balances, monitors shelf-life expiration, and issues proactive warnings to prevent food waste.

---

## 📌 Project Milestone Status (75% Estimated Completion)

This project is organized into three distinct development milestones:

| Phase | Description | Completion Status |
| :--- | :--- | :---: |
| **Phase 1 (40%)** | **Core Architecture & Foundation**: Relational SQLite database, derived stock calculation, shelf-life batches, master catalogue, inward procurement and live stock monitoring. | **✅ Complete** |
| **Phase 2 (30%)** | **Operations & Spoilage**: POS sales entry, validated spoilage write-offs, FIFO batch allocations, cost-of-goods-sold and wastage-loss accounting, date-range reports. | **✅ Complete** |
| **Phase 3 foundation (5%)** | **Basic Analytics Preparation**: Daily and period summaries for sales, purchases and wastage. This is reporting groundwork, not predictive analytics. | **✅ Complete** |
| **Phase 3 remaining (25%)** | **AI Reorder & Advanced Analytics**: Demand forecasting, perishable decay penalties, supplier-quality analysis and exportable reports. | **⏳ Remaining** |

---

The 75% figure is an estimate based on the original 40% / 30% / 30% phase weights: Phase 1 (40%) + Phase 2 (30%) + a clearly limited 5% of Phase 3 reporting groundwork. Forecasting is not represented as complete.

## 🛠️ Technology Stack

- **Frontend & UI**: Streamlit
- **Database**: SQLite3 (Embedded, Local, Zero-configuration, No internet required)
- **Data Manipulation**: Pandas
- **Language**: Python 3.10+ (Verified on Python 3.14)

---

## 📂 Project Structure

```text
├── database.py              # SQLite engine, schema definition, CRUD & stock logic
├── seed_data.py             # Realistic perishable vegetable sample data seeder
├── app.py                   # Main Streamlit web application
├── tests/test_phase2.py     # FIFO, loss-cost and stock-guard tests
├── PHASE_2_REPORT.txt       # Submission-ready Phase 2 report
├── requirements.txt         # Project dependencies
├── perishable_inventory.db  # Local SQLite database file (auto-generated)
└── README.md                # Project documentation and run guide
```

---

## 🚀 Setup & Execution Instructions

### 1. Prerequisites
Ensure Python is installed on your system.

### 2. Install Required Dependencies
Open a terminal / PowerShell in the project directory and run:

```bash
py -3.14 -m pip install -r requirements.txt
```
*(Or simply `pip install -r requirements.txt` if using your default Python environment)*

### 3. Populate Sample Data (Optional)
To replace the database with fresh, date-relative demonstration data (Spinach, Tomatoes, Potatoes, Onions, etc.):

```bash
py -3.14 seed_data.py
```

**Warning:** the seeder resets the local database. Back up `perishable_inventory.db` first if it contains real transactions.

### 4. Run the Streamlit Application
Launch the local web server:

```bash
py -3.14 -m streamlit run app.py
```

Streamlit will launch in your default web browser at `http://localhost:8501`.

### 5. Run the Phase 2 checks
From the project directory:

```bash
py -3.14 -m unittest discover -s tests -v
```

---

## 🗄️ Database Design

The system uses an embedded SQLite database (`perishable_inventory.db`) with four core ledger tables and two FIFO allocation tables:

1. **`vegetables`**:
   - `id`: Primary key
   - `name`: Vegetable name (unique)
   - `category`: Classification (Leafy Greens, Fruit Vegetable, Tubers, etc.)
   - `shelf_life_days`: Typical perishable shelf life in days
   - `reorder_threshold_kg`: Minimum safe threshold before reorder alert
   - `optimal_temp_celsius`: Storage temperature recommendation

2. **`purchases`**:
   - `id`: Primary key
   - `veg_id`: Foreign key referencing `vegetables(id)`
   - `purchase_date`: Inward arrival date
   - `quantity_kg`: Inward shipment quantity
   - `cost_per_kg`: Procurement unit cost
   - `batch_code`: Unique lot identifier
   - `expiry_date`: Automatically computed as `purchase_date + shelf_life_days`

3. **`sales`**:
   - `id`: Primary key
   - `veg_id`: Foreign key referencing `vegetables(id)`
   - `sale_date`: Transaction date
   - `quantity_kg`: Sold quantity
   - `selling_price_per_kg`: Retail price
   - `revenue`: Total proceeds

4. **`wastage`**:
   - `id`: Primary key
   - `veg_id`: Foreign key referencing `vegetables(id)`
   - `record_date`: Disposal date
   - `quantity_kg`: Discarded spoilage quantity
   - `reason`: Classification (rotting, transit damage, fungal spots)
   - `loss_cost`: Financial loss at the purchase cost of the consumed batches
   - `notes`: Optional audit detail

5. **`sale_batch_allocations`**: Links each sale to the purchase batches it consumed and records kilograms allocated from each batch.
6. **`wastage_batch_allocations`**: Links each write-off to the purchase batches consumed, allowing accurate FIFO loss valuation.

Phase 1 databases are upgraded when `init_db()` runs. Historical sale and wastage records are backfilled against eligible purchase batches in date order; existing stock is preserved.

---

## 📐 Mathematical Stock Balance Engine

Rather than relying on static or fragile counters, stock is computed directly from transactional logs using the conservation of inventory:

$$\text{Current Stock} = \sum(\text{Purchased}) - \sum(\text{Sold}) - \sum(\text{Wasted})$$

- **Batch Expiry Calculation**:
$$\text{Expiry Date} = \text{Purchase Date} + \text{Shelf Life (Days)}$$
- **Days Remaining**:
$$\text{Days Remaining} = \text{Expiry Date} - \text{Current Date}$$
- **FIFO allocation**: a sale or write-off is assigned to the oldest eligible purchase batch first. Each allocation records its quantity and source purchase cost.
- **Sale cost and margin**:
$$\text{COGS} = \sum(\text{Allocated Quantity} \times \text{Batch Purchase Cost/kg})$$
$$\text{Gross Margin} = \text{Sales Revenue} - \text{COGS}$$
- **Wastage loss**:
$$\text{Wastage Loss} = \sum(\text{Written-off Quantity from Batch} \times \text{Batch Purchase Cost/kg})$$

---

## 🎮 Realistic Demo Walkthrough

1. **Open the Application**: Open `http://localhost:8501`.
2. **Review Live Inventory**: Review stock, low-stock and expiry warnings, today's sales revenue, and today's loss value.
3. **Inspect Batches**: Select a vegetable in the inventory view to compare each batch's received quantity with its remaining FIFO balance.
4. **Log Inward Stock**: Open **Inward Stock**, select a vegetable, enter its delivery quantity and purchase cost, then observe its computed expiry date.
5. **Record a Sale**: In **Sales & Write-offs**, select **Record a Sale**, enter quantity and selling price, and review revenue, FIFO cost, and gross margin.
6. **Record Spoilage**: Select a write-off reason and quantity. The stored loss is computed from the purchase cost of the FIFO batches consumed.
7. **Review the Ledger and Period Summary**: Use **Operations Report** to select a date range and compare sales revenue, procurement cost, wasted quantity and wastage cost.
8. **Add New Commodity**: In **Vegetable Master Catalog**, register a commodity with its shelf life, reorder threshold and recommended storage temperature.

---

## ✅ Phase 2 Operations and Data Integrity

- Sales and write-offs are persisted as transactions; live stock remains derived from purchases minus sales and wastage.
- Both operations run inside SQLite write transactions and reject quantities beyond the remaining eligible stock.
- Sales exclude expired stock. Write-offs may consume expired stock so it can be cleared from the ledger.
- Each sale and write-off stores batch allocations in separate relational tables. Allocation records make partial batch depletion auditable and ensure the cost follows the source lot.
- Purchase cost flows into sale cost of goods sold and gross margin. Write-off loss is calculated from allocated batch cost, not a manually entered estimate.
- The date-range report and unified ledger summarize sale revenue, purchase spend, lost quantity and FIFO-valued wastage.
- The database engine uses the `Asia/Kolkata` business date for expiry and daily summaries.

The Replit browser preview is a separate companion implementation for reviewing the same Phase 2 workflows. It uses its own local SQLite database and does **not** synchronize records with the offline Streamlit database.
