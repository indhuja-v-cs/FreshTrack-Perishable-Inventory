# 🌱 FreshTrack: Perishable Vegetable Inventory & Wastage Reduction System

A local, lightweight, and self-contained inventory management application specifically designed for perishable agricultural commodities (vegetables, greens, roots, and tubers). It tracks inward procurement batches, computes real-time stock balances, monitors shelf-life expiration, and issues proactive warnings to prevent food waste.

---

## 📌 Project Milestone Status (40% Completed)

This project is organized into three distinct development milestones:

| Phase | Description | Completion Status |
| :--- | :--- | :---: |
| **Phase 1 (40%)** | **Core Architecture & Foundation**: Relational SQLite database, mathematical stock calculation engine, dynamic shelf-life batch tracking, master catalog CRUD, inward procurement recording, and live stock monitoring dashboard. | **✅ 100% Complete** |
| **Phase 2 (30%)** | **Operations & Spoilage**: Daily POS sales recording terminal, spoilage/wastage write-off interface, loss cost accounting, and FIFO batch depletion. | ⏳ Planned |
| **Phase 3 (30%)** | **AI Reorder & Analytics**: Machine learning demand forecasting, perishable decay penalties, smart restock recommendations, and interactive visual charts. | ⏳ Planned |

---

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
To pre-load realistic perishable items (Spinach, Tomatoes, Potatoes, Onions, etc.) with inward batches and transactions:

```bash
py -3.14 seed_data.py
```

### 4. Run the Streamlit Application
Launch the local web server:

```bash
py -3.14 -m streamlit run app.py
```

Streamlit will launch in your default web browser at `http://localhost:8501`.

---

## 🗄️ Database Design

The system uses an embedded SQLite database (`perishable_inventory.db`) with 4 relational tables:

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
   - `loss_cost`: Financial loss valuation

---

## 📐 Mathematical Stock Balance Engine

Rather than relying on static or fragile counters, stock is computed directly from transactional logs using the conservation of inventory:

$$\text{Current Stock} = \sum(\text{Purchased}) - \sum(\text{Sold}) - \sum(\text{Wasted})$$

- **Batch Expiry Calculation**:
$$\text{Expiry Date} = \text{Purchase Date} + \text{Shelf Life (Days)}$$
- **Days Remaining**:
$$\text{Days Remaining} = \text{Expiry Date} - \text{Current Date}$$

---

## 🎮 Realistic Demo Walkthrough

1. **Open the Application**: Open `http://localhost:8501`.
2. **Review Live Inventory**: Notice high-perishable spinach flagged as **EXPIRING SOON** (1 day left) and cauliflower as **LOW STOCK**.
3. **Inspect Batches**: Use the dropdown at the bottom of the overview tab to inspect individual purchase batches and codes.
4. **Log Inward Stock**: Switch to the **Inward Stock** tab, choose *Tomato (Tamatar)*, enter 30 kg, and click **Inward Stock**. Observe the auto-calculated expiry date and instant update to live inventory.
5. **Add New Commodity**: Navigate to **Vegetable Master Catalog**, register *Bitter Gourd (Karela)* with 5 days shelf life, and observe it appear in the catalog table.
