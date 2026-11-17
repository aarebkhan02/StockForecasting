import math
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data-rms" / "data-rms"

# Master dataset and forecasting loaders
from replenishment_engine import (
    load_master_datasets,
    generate_holt_winters_forecasts,
    compute_all_replenishment_metrics,
)

import importlib
import spoilage_engine
importlib.reload(spoilage_engine)
from spoilage_engine import (
    compute_all_spoilage_metrics,
    get_recipe_wastage_comparison,
)

try:
    import ui_theme
    importlib.reload(ui_theme)
    from ui_theme import (
        style_reorder_status,
        style_usable_ss_status,
        style_usable_ss_deficit,
    )
except ImportError:
    def style_reorder_status(val):
        if val == "Reorder Required":
            return "background-color: #fee2e2; color: #991b1b; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        elif val == "No Reorder Required":
            return "background-color: #d1fae5; color: #065f46; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        elif val == "Unknown":
            return "background-color: #f1f5f9; color: #475569; font-weight: 500; border-radius: 4px; padding: 2px 6px;"
        return ""

    def style_usable_ss_status(val):
        if val == "Protected":
            return "background-color: #d1fae5; color: #065f46; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        elif val == "Deficit":
            return "background-color: #fee2e2; color: #991b1b; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        return ""

    def style_usable_ss_deficit(val):
        if isinstance(val, (int, float)) and val > 0:
            return "background-color: #fef2f2; color: #b91c1c; font-weight: 700;"
        elif isinstance(val, str) and not val.strip().startswith("0.00") and not val.strip() == "0":
            return "background-color: #fef2f2; color: #b91c1c; font-weight: 700;"
        return ""


# -----------------------------
# 0. Page Configuration & Setup
# -----------------------------
st.set_page_config(
    page_title="Spoilage Forecasting - Restaurant RMS",
    page_icon="🥀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load master restaurant data
stock = pd.read_csv(DATA_DIR / "stock_balance.csv")
ingredients = pd.read_csv(DATA_DIR / "ingredient.csv")
uom = pd.read_csv(DATA_DIR / "unit_of_measure.csv")

# Load master datasets
master_data = load_master_datasets(BASE_DIR)

# -----------------------------
# 1. In-Memory Simulated Inventory Session State
# -----------------------------
if "simulated_stock" not in st.session_state:
    st.session_state.simulated_stock = stock.copy()

if "order_confirmed_msg" not in st.session_state:
    st.session_state.order_confirmed_msg = None

if "last_deduction_summary" not in st.session_state:
    st.session_state.last_deduction_summary = None

if "last_order_key" not in st.session_state:
    st.session_state.last_order_key = None

if "confirmed_order_key" not in st.session_state:
    st.session_state.confirmed_order_key = None

# -----------------------------
# 2. Sidebar Configuration Controls
# -----------------------------
with st.sidebar:
    st.markdown("###  Navigation")
    st.page_link("app.py", label="Replenishment Dashboard")
    st.page_link("pages/1_Place_Customer_Order.py", label="Place Customer Order", icon="🛒")
    st.page_link("pages/2_Spoilage_Forecasting.py", label="Spoilage Forecasting", icon="🥀")
    st.divider()

    st.header(" Spoilage & Policy Controls")
    st.caption("Configurable parameters shared with replenishment engine.")

    # Service-level factor control
    st.subheader("1. Service Level Factor (z)")
    z_selection = st.selectbox(
        "Target Service Level",
        options=[
            "95% (z = 1.645) - Standard Default",
            "90% (z = 1.280)",
            "99% (z = 2.326)",
            "Custom Factor"
        ],
        index=0,
        help="One-sided normal factor for safety stock calculation."
    )
    if "95%" in z_selection:
        z_score = 1.645
    elif "90%" in z_selection:
        z_score = 1.280
    elif "99%" in z_selection:
        z_score = 2.326
    else:
        z_score = st.number_input("Custom z value", min_value=0.5, max_value=4.0, value=1.645, step=0.05)

    st.caption(f"Active Service Factor: **z = {z_score:.3f}**")

    # Replenishment Review Period control
    st.subheader("2. Review Period (R)")
    review_period = st.number_input(
        "Review Period R (Days)",
        min_value=0.5,
        max_value=14.0,
        value=1.0,
        step=0.5,
        help="Time between inventory review opportunities."
    )
    st.caption(f"Active Review Period: **R = {review_period:.1f} days**")

    # Risk-Assessment Horizon control
    st.subheader("3. Horizon (H)")
    risk_horizon = st.slider(
        "Simulation Horizon H (Days)",
        min_value=3,
        max_value=14,
        value=7,
        step=1,
        help="Window in days over which FEFO batch consumption and expiry are simulated."
    )
    st.caption(f"Active Horizon: **H = {risk_horizon} days**")

    st.divider()

    # Inventory Session Control
    st.subheader("🔄 Operational Stock Control")
    st.caption("Calculations operate on in-memory simulated stock. Original CSV files remain untouched.")
    if st.button("Reset Demo Inventory", type="secondary", use_container_width=True):
        st.session_state.simulated_stock = stock.copy()
        st.session_state.order_confirmed_msg = None
        st.session_state.last_deduction_summary = None
        st.session_state.confirmed_order_key = None
        st.success("Simulated stock restored to original starting balance.")
        st.rerun()

    st.divider()
    st.markdown(
        """
        **Snapshot Metadata:**
        - **Historical Data End:** 2026-09-22
        - **Forecast Window:** 2026-09-23 to 2026-09-29
        - **Allocation Policy:** FEFO (First Expire, First Out)
        - **Batch Source:** `goods_receipt_item.csv` (1,127 actual receipts)
        - **Documented Expiry Rule:** Batches expire on `expiry_date`
        """
    )

# -----------------------------
# 3. Dynamic Calculation Engine
# -----------------------------
# Generate Holt-Winters forecasts
forecast_results = generate_holt_winters_forecasts(
    master_data["demand_df"],
    horizon=risk_horizon
)

# Baseline replenishment metrics (using live simulated stock)
replenishment_metrics = compute_all_replenishment_metrics(
    st.session_state.simulated_stock,
    master_data,
    forecast_results,
    z_score=z_score,
    review_period=review_period,
    risk_horizon=risk_horizon,
)

# Expiry-aware and spoilage metrics
spoilage_results = compute_all_spoilage_metrics(
    st.session_state.simulated_stock,
    master_data,
    forecast_results,
    replenishment_metrics,
    review_period=review_period,
    risk_horizon=risk_horizon,
    base_dir=BASE_DIR
)

daily_forecast_df = spoilage_results["daily_forecast_df"]
reorder_df = spoilage_results["reorder_df"]
tech_df = spoilage_results["technical_summary_df"]
forecast_dates = spoilage_results["forecast_dates"]
latest_date = spoilage_results["latest_date"]
forecast_range_str = f"{forecast_dates[0]:%Y-%m-%d} to {forecast_dates[-1]:%Y-%m-%d}"

# -----------------------------
# 4. Page Header & Demo Banner
# -----------------------------
st.title(" Spoilage Forecasting & Expiry-Aware Replenishment")
st.caption(
    f"Simulating **First Expire, First Out (FEFO)** batch consumption, **projected expiry waste**, "
    f"**usable inventory exclusion**, and **expiry-adjusted replenishment order policies**. "
    f"*(Snapshot Date: **2026-09-22** | Forecast Window: **{forecast_range_str}**)*"
)

# Strict Data Safety / Simulation Mode Notice
st.info(
    " **Demo / Simulation Mode**: All calculations are strictly read-only and operate on in-memory "
    "operational stock copies (`st.session_state.simulated_stock`). Original CSV files, database records, "
    "and transactions are never modified or overwritten. No purchase orders are automatically placed.",
    icon="ℹ️"
)

# -----------------------------
# 5. Top KPI Summary Cards
# -----------------------------
kpi_c1, kpi_c2, kpi_c3, kpi_c4, kpi_c5 = st.columns(5)

with kpi_c1:
    st.metric(
        label="Tracked Ingredients",
        value=len(tech_df),
        help="Total inventory master ingredients tracked in RMS."
    )

with kpi_c2:
    st.metric(
        label=" Ingredients with Spoilage",
        value=spoilage_results["ingredients_with_spoilage"],
        help="Ingredients having batches projected to expire unconsumed within the forecast horizon."
    )

with kpi_c3:
    st.metric(
        label=" Projected Expiry Waste",
        value=f"{spoilage_results['total_spoilage_qty']:.2f} units",
        help="Total quantity projected to expire unconsumed under FEFO demand allocation."
    )

with kpi_c4:
    st.metric(
        label=" Expiry Waste Cost",
        value=f"₹{spoilage_results['total_spoilage_cost']:,.2f}",
        help="Financial valuation of projected expiry waste calculated using verified batch unit costs."
    )

with kpi_c5:
    st.metric(
        label="⚠️ Accelerated Stockouts",
        value=spoilage_results["accelerated_stockouts_count"],
        help="Ingredients where batch expiry causes stockout earlier than standard non-expiry projection."
    )

# -----------------------------
# 6. Section A: Daily Demand & Spoilage Forecast Table
# -----------------------------
st.markdown("---")
st.subheader("1. Daily Demand & Spoilage Forecast")
st.caption(
    "Displaying daily forecast demand, estimated recipe preparation waste allowance, expiring stock quantities "
    "according to documented expiry rules, projected usable inventory balances, unmet demand, historical full-delivery lead times, "
    "and expiry-aware reorder status (1 row per ingredient per forecast date)."
)

# Filters for Daily Table
filter_c1, filter_c2, filter_c3 = st.columns([2.5, 2, 2.5])
with filter_c1:
    all_ing_names = sorted(daily_forecast_df["_ingredient_name"].unique())
    selected_ingredients = st.multiselect(
        "Filter by Ingredient",
        options=all_ing_names,
        default=[],
        placeholder="All Ingredients",
        help="Leave empty to display all 14 ingredients."
    )
with filter_c2:
    all_dates = sorted(daily_forecast_df["Date"].unique())
    date_options = ["All Forecast Dates"] + all_dates
    selected_date = st.selectbox(
        "Filter by Forecast Date",
        options=date_options,
        index=0,
        help="Show all dates or select a specific forecast date."
    )
with filter_c3:
    st.markdown("<div style='height: 1.7rem;'></div>", unsafe_allow_html=True)
    show_risk_only = st.checkbox(
        "Show Spoilage or Shortage Days Only",
        value=False,
        help="Filter to rows where Expiring Quantity > 0 or Unmet Demand > 0."
    )

# Apply filters
filtered_daily_df = daily_forecast_df.copy()

if selected_ingredients:
    filtered_daily_df = filtered_daily_df[
        filtered_daily_df["_ingredient_name"].isin(selected_ingredients)
    ]

if selected_date != "All Forecast Dates":
    filtered_daily_df = filtered_daily_df[
        filtered_daily_df["Date"] == selected_date
    ]

if show_risk_only:
    filtered_daily_df = filtered_daily_df[
        filtered_daily_df["_has_spoilage_or_shortage"]
    ]

# Essential columns required by specification
essential_daily_cols = [
    "Date",
    "Ingredient",
    "Lead Time (Days)",
    "Reorder Status",
    "Shelf Life",
    "Current Usable Stock",
    "Daily Forecast Demand",
    "Estimated Preparation Waste",
    "Days Until Expiry",
    "Expiring Quantity",
    "Projected Usable Stock",
    "Unmet Demand",
]

display_daily_table = filtered_daily_df[essential_daily_cols].copy()

# Cell styling for daily table
def style_spoilage_qty(val):
    if isinstance(val, (int, float)) and val > 0:
        return "background-color: #ffebee; color: #b71c1c; font-weight: bold;"
    return ""

def style_unmet_demand(val):
    if isinstance(val, (int, float)) and val > 0:
        return "background-color: #fff3e0; color: #e65100; font-weight: bold;"
    return ""

def style_days_until_expiry(val):
    if isinstance(val, str) and "Expired" in val:
        return "background-color: #ffebee; color: #b71c1c; font-weight: bold;"
    return ""

def style_lead_time(val):
    if val == "N/A":
        return "color: #94a3b8; font-style: italic;"
    return ""

if not display_daily_table.empty:
    styled_daily = (
        display_daily_table.style
        .format({
            "Current Usable Stock": "{:.2f}",
            "Daily Forecast Demand": "{:.2f}",
            "Estimated Preparation Waste": "{:.2f}",
            "Expiring Quantity": "{:.2f}",
            "Projected Usable Stock": "{:.2f}",
            "Unmet Demand": "{:.2f}",
        })
        .map(style_spoilage_qty, subset=["Expiring Quantity"])
        .map(style_unmet_demand, subset=["Unmet Demand"])
        .map(style_days_until_expiry, subset=["Days Until Expiry"])
        .map(style_reorder_status, subset=["Reorder Status"])
        .map(style_lead_time, subset=["Lead Time (Days)"])
    )
    st.dataframe(
        styled_daily,
        use_container_width=True,
        height=450,
        hide_index=True,
        column_config={
            "Lead Time (Days)": st.column_config.TextColumn(
                "Lead Time (Days)",
                help="Historical full-delivery lead time from full_lead_time_summary.csv (avg_full_lead_time_days), rounded to the nearest whole day. Consistent across all forecast dates for the ingredient."
            ),
            "Reorder Status": st.column_config.TextColumn(
                "Reorder Status",
                help="Replenishment recommendation status based on existing expiry-aware logic (Reorder Required when order recommended, No Reorder Required when order is 0, Unknown when data unavailable)."
            ),
        }
    )
    st.caption("ℹ️ *Lead Time (Days) comes from historical full-delivery data (`full_lead_time_summary.csv` authoritative field `avg_full_lead_time_days`) and is rounded to the nearest whole day. Reorder Status reflects the existing expiry-aware replenishment recommendation.*")
else:
    st.info("No forecast records match the selected filters.")




# -----------------------------
# 7. Section B: Expiry-Aware Reorder Recommendations Table
# -----------------------------
st.markdown("---")
st.subheader("2. Expiry-Aware Reorder Recommendations")
st.caption(
    "Replenishment recommendations calculated from projected usable inventory. "
    "Adjusts for stock that will expire before it can satisfy future demand, shown side-by-side with baseline recommendations. "
    "Orders are never placed automatically."
)

filtered_reorder_df = reorder_df.copy()

essential_reorder_cols = [
    "Ingredient",
    "Usable Stock at Expected Delivery",
    "Forecast Requirement",
    "Expected Expiry Waste",
    "Baseline Recommended Order",
    "Recommended Order Quantity",
    "Usable Safety Stock Status",
    "Safety Stock Deficit (kg/L)",
]

# Visible warning when usable stock at expected delivery falls below required safety stock
deficit_items = filtered_reorder_df[filtered_reorder_df["usable_safety_stock_status"] == "Deficit"]
if not deficit_items.empty:
    deficit_details = ", ".join([
        f"**{r['_ingredient_name']}** ({r['usable_safety_stock_deficit']:.2f} {r['_uom_code']} deficit)"
        for _, r in deficit_items.iterrows()
    ])
    st.warning(
        f"⚠️ **Usable Safety Stock Deficit Alert:** {len(deficit_items)} ingredient(s) have projected usable stock at delivery falling below required safety stock: {deficit_details}.",
        icon="⚠️"
    )

display_reorder_table = filtered_reorder_df[essential_reorder_cols].copy()
# Format displayed deficit using each ingredient's base UOM
display_reorder_table["Safety Stock Deficit (kg/L)"] = [
    f"{r['usable_safety_stock_deficit']:.2f} {r['_uom_code']}"
    for _, r in filtered_reorder_df.iterrows()
]

def style_reorder_adj(val, diff):
    if diff > 0:
        return "background-color: #e8f5e9; color: #1b5e20; font-weight: bold;"
    return ""

def highlight_adjusted_rows(row):
    q_adj = row["Recommended Order Quantity"]
    q_base = row["Baseline Recommended Order"]
    if q_adj > q_base:
        return ["background-color: #f0fdf4; color: #166534; font-weight: 600;" if col == "Recommended Order Quantity" else "" for col in row.index]
    return ["" for _ in row.index]

if not display_reorder_table.empty:
    styled_reorder = (
        display_reorder_table.style
        .format({
            "Usable Stock at Expected Delivery": "{:.2f}",
            "Forecast Requirement": "{:.2f}",
            "Expected Expiry Waste": "{:.2f}",
            "Baseline Recommended Order": "{:.2f}",
            "Recommended Order Quantity": "{:.2f}",
        })
        .map(style_spoilage_qty, subset=["Expected Expiry Waste"])
        .map(style_usable_ss_status, subset=["Usable Safety Stock Status"])
        .map(style_usable_ss_deficit, subset=["Safety Stock Deficit (kg/L)"])
        .apply(highlight_adjusted_rows, axis=1)
    )
    st.dataframe(styled_reorder, use_container_width=True, hide_index=True)
else:
    st.info("No ingredients require an expiry-adjusted order.")

st.caption("ℹ️ *Expected Expiry Waste represents unusable stock projected to expire within the lead time + review period coverage window (L_i + R). Usable Safety Stock Status verifies whether unexpired inventory at expected delivery date safely maintains the required safety stock buffer.*")



st.divider()
st.page_link("app.py", label="← Return to Replenishment Dashboard", icon="📊")
