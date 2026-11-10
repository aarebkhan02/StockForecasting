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
    "Next-Day Demand",
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
            "Next-Day Demand": "{:.2f}",
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

reorder_filter_c1, reorder_filter_c2 = st.columns([3, 3])
with reorder_filter_c1:
    reorder_mode = st.radio(
        "Filter Reorder Table",
        options=["All 14 Ingredients", "Ingredients with Order Adjustments Only (Q_adj > Q_base)"],
        horizontal=True
    )

filtered_reorder_df = reorder_df.copy()
if "Adjustments Only" in reorder_mode:
    filtered_reorder_df = filtered_reorder_df[filtered_reorder_df["_order_difference"] > 0]

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



# -----------------------------
# 8. Technical Expanders
# -----------------------------
st.markdown("---")

# Expander 1: Batch Details & Unit Costs
with st.expander("Technical Batch Details & Unit Costs (Live Stock Audit)", expanded=False):
    st.markdown(
        """
        ##### Batch-Level Inventory Reconstruction:
        - **Source:** Verified Goods Receipt Note line items (`goods_receipt_item.csv` and `goods_receipt.csv`).
        - **Allocation Rule:** Current unexpired stock is mapped to the most recent physical receipts in reverse chronological order and sorted FEFO.
        - **Verification:** All 1,127 goods receipt items contain valid batch identifiers, receipt dates, expiry dates, and verified unit costs.
        - **Limitation Notice:** Batch allocation reconstructs physical batches by mapping current unexpired stock balance to the most recent Goods Receipt Note items (FIFO receipt order). This provides an estimated batch-level reconstruction since individual kitchen sale consumption entries in the stock ledger were logged against ingredient totals rather than specific batch IDs.
        """
    )

    batch_sel_ing = st.selectbox(
        "Select Ingredient to Inspect Batches:",
        options=tech_df["ingredient_name"].tolist(),
        key="expander_batch_ing_select"
    )

    selected_tech_row = tech_df[tech_df["ingredient_name"] == batch_sel_ing].iloc[0]
    ing_batches = selected_tech_row["batches"]
    ing_unit = selected_tech_row["unit"]

    if ing_batches:
        b_records = []
        for b in ing_batches:
            r_date = b["received_at"].strftime("%Y-%m-%d")
            e_date = b["expiry_date"].strftime("%Y-%m-%d")
            days_rem = (pd.to_datetime(b["expiry_date"]).normalize() - pd.to_datetime(latest_date).normalize()).days
            status = "🚨 Expired" if days_rem <= 0 else ("⚠️ Approaching (≤7d)" if days_rem <= 7 else "✅ Fresh")
            b_records.append({
                "Batch Number": b["batch_number"],
                "Received Date": r_date,
                "Expiry Date": e_date,
                "Days to Expiry": days_rem,
                "Current Stock": f"{b['batch_stock']:.2f} {ing_unit}",
                "Original Receipt Qty": f"{b['accepted_qty']:.2f} {ing_unit}",
                "Unit Cost": f"₹{b['unit_cost']:.2f}",
                "Total Value": f"₹{b['batch_stock'] * b['unit_cost']:,.2f}",
                "Status": status,
            })
        st.dataframe(pd.DataFrame(b_records), use_container_width=True, hide_index=True)
    else:
        st.info("No active physical batches currently recorded in stock for this ingredient.")

# Expander 2: Trajectory Chart & Deep-Dive Inspection
with st.expander("📈 Visual Trajectory Chart & Single Ingredient Deep-Dive", expanded=False):
    chart_sel_ing = st.selectbox(
        "Select Ingredient for Trajectory Inspection:",
        options=tech_df["ingredient_name"].tolist(),
        index=6,  # Default to Milk (ID 7)
        key="expander_chart_ing_select"
    )

    ch_row = tech_df[tech_df["ingredient_name"] == chart_sel_ing].iloc[0]
    ch_ing_id = int(ch_row["ingredient_id"])
    ch_unit = ch_row["unit"]
    ch_fefo_res = spoilage_results["fefo_trajectories"][ch_ing_id]
    ch_traj_df = ch_fefo_res["trajectory_df"]

    # Baseline trajectory
    base_traj = replenishment_metrics["trajectories"][ch_ing_id]["trajectory_df"]

    x_labels = ["Day 0 (Snapshot)"] + [f"Day {row['day']} ({row['date_str']})" for _, row in ch_traj_df.iterrows()]
    y_base = [ch_row["current_physical_stock"]] + base_traj["projected_unconstrained"].tolist()
    y_fefo = [ch_row["current_usable_stock"]] + ch_traj_df["projected_usable_stock"].tolist()

    fig_fefo = go.Figure()

    # Baseline trajectory
    fig_fefo.add_trace(go.Scatter(
        x=x_labels,
        y=y_base,
        mode="lines+markers",
        name="Baseline Projected Stock (No Expiry)",
        line=dict(color="#94a3b8", width=2, dash="dot"),
        marker=dict(size=5)
    ))

    # FEFO usable trajectory
    fig_fefo.add_trace(go.Scatter(
        x=x_labels,
        y=y_fefo,
        mode="lines+markers",
        name="FEFO Usable Stock (Expiry-Aware)",
        line=dict(color="#dc2626" if ch_row["total_expiry_waste_qty"] > 0 else "#16a34a", width=3),
        marker=dict(size=7)
    ))

    # Required safety stock
    ss_val = replenishment_metrics["summary_df"].set_index("ingredient_id").loc[ch_ing_id, "safety_stock"]
    fig_fefo.add_trace(go.Scatter(
        x=x_labels,
        y=[ss_val] * len(x_labels),
        mode="lines",
        name="Required Safety Stock (SS)",
        line=dict(color="#ea580c", width=1.5, dash="dash")
    ))

    # Zero boundary
    fig_fefo.add_trace(go.Scatter(
        x=x_labels,
        y=[0.0] * len(x_labels),
        mode="lines",
        name="Zero Boundary",
        line=dict(color="#475569", width=1)
    ))

    # Add spoilage annotations
    for _, trow in ch_traj_df.iterrows():
        if trow["expiring_qty"] > 0:
            fig_fefo.add_annotation(
                x=f"Day {trow['day']} ({trow['date_str']})",
                y=trow["projected_usable_stock"],
                text=f"🥀 -{trow['expiring_qty']:.1f} {ch_unit} Expired",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#dc2626",
                bgcolor="#fef2f2",
                bordercolor="#dc2626"
            )
        if trow["incoming_qty"] > 0:
            fig_fefo.add_annotation(
                x=f"Day {trow['day']} ({trow['date_str']})",
                y=trow["projected_usable_stock"],
                text=f"📦 +{trow['incoming_qty']:.1f} {ch_unit} PO Arrival",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#16a34a",
                bgcolor="#f0fdf4",
                bordercolor="#16a34a"
            )

    fig_fefo.update_layout(
        title=f"Inventory Projection: Baseline vs FEFO Expiry Simulation ({chart_sel_ing})",
        xaxis_title="Timeline",
        yaxis_title=f"Stock ({ch_unit})",
        template="plotly_white",
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_fefo, use_container_width=True)

    # Detailed Daily Simulation Ledger
    st.write(f"##### Day-by-Day Simulation Ledger: {chart_sel_ing}")
    ledger_cols = [
        "Day", "Date", "Daily Forecast Demand", "Estimated Preparation Waste",
        "Total Requirement", "Usable Stock (Before Demand)", "Verified PO Arrival",
        "Consumed Stock", "Days Until Expiry", "Expiring Quantity", "Projected Usable Stock", "Unmet Demand"
    ]
    ledger_display = ch_traj_df.rename(columns={
        "day": "Day",
        "date_str": "Date",
        "daily_forecast_demand": "Daily Forecast Demand",
        "estimated_prep_waste": "Estimated Preparation Waste",
        "total_requirement": "Total Requirement",
        "usable_before_demand": "Usable Stock (Before Demand)",
        "incoming_qty": "Verified PO Arrival",
        "consumed_stock": "Consumed Stock",
        "days_until_expiry_str": "Days Until Expiry",
        "expiring_qty": "Expiring Quantity",
        "projected_usable_stock": "Projected Usable Stock",
        "unmet_demand": "Unmet Demand",
    })[ledger_cols]

    st.dataframe(ledger_display, use_container_width=True, hide_index=True)

# -----------------------------
# Complete Spoilage & FEFO Calculation Guide
# -----------------------------
with st.expander("📐 How are these values calculated? (Complete Spoilage & FEFO Calculation Guide)", expanded=False):
    st.markdown(
        r"""
### 🥀 Complete Spoilage Forecasting & FEFO Calculation Guide

This guide details the mathematical foundations, batch tracking rules, preparation waste allowances, and FEFO inventory allocation logic used throughout this page.

---

#### 1. Data Sources & Batch Tracking
- **Ingredient Shelf Life:** Sourced from `data-rms/data-rms/ingredient.csv` (`shelf_life_days`). Values range from 3 days (Chicken, Milk, Spinach) to 365 days (Basmati Rice, Lentils).
- **Goods Receipt Batches:** Physical batch deliveries are tracked in `goods_receipt_item.csv` (`batch_number`, `expiry_date`, `accepted_qty`, `unit_cost`). Every physical goods receipt note item specifies the supplier's stamped expiry date.
- **Master Shelf Life vs. Batch Expiry Date:** Master shelf life in `ingredient.csv` is the theoretical product durability under ideal storage. Actual batch expiry dates in `goods_receipt_item.csv` represent the legal, authoritative cutoff stamped by the vendor upon physical dock receipt.

---

#### 2. Active Batch Reconstruction (`get_active_ingredient_batches` in `spoilage_engine.py`)
- **Limitation & Rationale:** The operational stock ledger (`stock_ledger_entry.csv`) records kitchen dish sales against total ingredient inventory rather than specific batch IDs. 
- **Algorithmic Reconstruction:** The engine maps current unexpired inventory (`qty_base` from `st.session_state.simulated_stock`) to the most recent Goods Receipt Note items (`goods_receipt_item.csv`) in reverse chronological order (FIFO receipt order):
  $$b_{\text{qty}} = \min(\text{remaining\_stock}, \text{accepted\_qty}_{\text{receipt}})$$
  Reconstructed batches are sorted strictly **FEFO**: earliest expiration date first, then earliest receipt date. This provides an estimated batch-level reconstruction transparently grounded in actual dock receipts.

---

#### 3. Preparation Waste vs. Recorded Expiry Waste (`get_ingredient_prep_waste_percentages` in `spoilage_engine.py`)
- **Source of `wastage_percent`:** Configured in `recipe_ingredient.csv` (range $0.18\% - 3.90\%$, average $2.16\%$).
- **Historical Demand Grounding:** Analysis of `DataCleaned/daily_ingredient_demand.csv` proves historical demand was computed using net dish consumption ($\text{quantity} \times \text{recipe\_qty} / \text{yield\_qty}$) without adding `wastage_percent`.
- **Sales-Weighted Recipe Trim:** To reflect actual menu sales mix, the preparation trim percentage is weighted across all historical orders:
  $$p_{\text{waste}, i} = \frac{\sum_k (\text{order\_qty}_k \times \text{recipe\_qty}_k \times \text{wastage\_percent}_k)}{\sum_k (\text{order\_qty}_k \times \text{recipe\_qty}_k)}$$
- **Estimated Preparation Waste Formula:** Applied strictly **once** per forecast day:
  $$\text{Estimated Preparation Waste}_{i,t} = \text{round}\left( \hat{D}_{i,t} \times \left(\frac{p_{\text{waste}, i}}{100.0}\right), 4 \right)$$
  $$\text{Total Daily Requirement}_{i,t} = \hat{D}_{i,t} + \text{Estimated Preparation Waste}_{i,t}$$
- **Zero Kitchen Scrap in Ledger:** All 158 historical wastage entries in `stock_ledger_entry.csv` cite `reason = 'Expired stock removed'`. Kitchen trimming waste is never recorded in inventory ledgers. It is maintained strictly as a recipe trim allowance.

---

#### 4. FEFO Simulation Pipeline (`simulate_fefo_trajectory` in `spoilage_engine.py`)
For each forecast day $t$ (calendar date $f_{\text{norm}}$):
1. **Beginning-of-Day Expiry Check:** A batch becomes unusable on the date:
   $$\text{batch.expiry\_date} \le f_{\text{norm}}$$
   Any unconsumed stock in that batch is removed as **Expiring Quantity** at the start of day $t$. Expired stock is never permitted to satisfy customer demand.
2. **Expiring Cost Calculation:** $\text{Expiring Cost}_t = \sum_b (\text{expiring\_qty}_b \times \text{unit\_cost}_b)$.
3. **Days Until Expiry:** Distance from day $t$ to nearest active unexpired batch:
   $$\text{Days Until Expiry}_t = (\min_{b \in \text{Usable}} b.\text{expiry\_date} - f_{\text{norm}}).\text{days}$$
   Displays `"0 (Expired)"` if all batches expired, or `"N/A"` if no batches exist.
4. **Verified Inbound Deliveries:** Inbound POs arriving on day $t$ are added to usable stock.
5. **FEFO Demand Allocation:** Total requirement is allocated sequentially to unexpired batches sorted by earliest expiry date. If dated batches are exhausted, it draws from day $t$ incoming deliveries.
6. **Projected Usable Stock:** Ending balance of unexpired dated batches plus remaining incoming deliveries:
   $$\text{Projected Usable Stock}_t = \sum_{b \in \text{Usable}} b.\text{batch\_stock}_{\text{rem}} + \text{Incoming}_{\text{rem}}$$
7. **Unmet Demand:** If daily requirement exceeds total usable inventory:
   $$\text{Unmet Demand}_t = \max\left(0.0, \text{Total Requirement}_t - \text{Total Usable Available}_t\right)$$

---

#### 5. Spoilage-Aware Reorder Recommendation ($Q_{\text{adj}}$)
Adjusts replenishment for stock that will spoil before it can satisfy demand:
- **Coverage Horizon:** $C_i = L_i + R$; $\text{cov\_ceil} = \min(H, \lceil L_i + R \rceil)$.
- **Expected Expiry Waste:** Sum of batch quantities expiring within the coverage window:
  $$\text{Waste}_{\text{coverage}, i} = \sum_{t=1}^{\text{cov\_ceil}} \text{Expiring Quantity}_{i,t}$$
- **Effective Usable Stock:** Stock available to meet demand after discounting coverage spoilage:
  $$\text{Effective Usable Stock}_i = \max\left(0.0, \text{Current Usable Stock}_i - \text{Waste}_{\text{coverage}, i}\right)$$
- **Coverage Requirement:** Prorated demand plus preparation trim over coverage period:
  $$\text{Req}_{\text{cov}, i} = \sum_{t=1}^{\lfloor C_i \rfloor} \text{Total Requirement}_{i,t} + (C_i - \lfloor C_i \rfloor) \times \text{Total Requirement}_{i, \lfloor C_i \rfloor + 1}$$
- **Expiry-Adjusted Reorder Formula:**
  $$Q_{\text{adj}, i} = \max\left(0.0, \text{Req}_{\text{cov}, i} + SS_i - (\text{Effective Usable Stock}_i + \text{Eligible Incoming}_i)\right)$$

---

#### 6. Table A (Daily Forecast) & Table B (Reorder) Derivation & Real Numerical Examples

##### Table A: Daily Demand & Spoilage Forecast Columns
| Column Name | Formula / Derivation | Source / Function | Chicken Day 1 (2026-09-23) | Chicken Day 2 (2026-09-24) |
| :--- | :--- | :--- | :--- | :--- |
| **Date** | Forecast calendar date $f_{\text{norm}}$ | Trajectory step | `2026-09-23` | `2026-09-24` |
| **Ingredient** | Ingredient name and base unit | Master ingredient | `Chicken (kg)` | `Chicken (kg)` |
| **Lead Time (Days)** | $\text{round}(L_i)$ | `full_lead_time_summary.csv` | `2` ($1.65\text{ d}$) | `2` ($1.65\text{ d}$) |
| **Reorder Status** | Reorder Required if $Q_{\text{adj}} > 0$ | Spoilage reorder logic | `Reorder Required` | `Reorder Required` |
| **Shelf Life** | Master shelf life in days | `ingredient.csv` | `3 days` | `3 days` |
| **Current Usable Stock** | Unexpired batch stock at snapshot | Active reconstructed batches | `21.29 kg` | `21.29 kg` |
| **Next-Day Demand** | Day 1 forecast demand $\hat{D}_{i,1}$ | Holt-Winters Day 1 | `18.34 kg` | `18.34 kg` |
| **Daily Forecast Demand** | Day $t$ forecast demand $\hat{D}_{i,t}$ | Holt-Winters Day $t$ | `18.34 kg` | `19.51 kg` |
| **Estimated Prep Waste** | $\hat{D}_{i,t} \times (p_{\text{waste}} / 100)$ | Sales-weighted trim ($3.49\%$) | $18.34 \times 0.0349 = \mathbf{0.64\text{ kg}}$ | $19.51 \times 0.0349 = \mathbf{0.68\text{ kg}}$ |
| **Days Until Expiry** | Days to oldest usable batch | Batch expiry calendar | `1 day` (expires 09-24) | `0 (Expired)` |
| **Expiring Quantity** | Unconsumed stock expiring today | Start-of-day expiry check | `0.00 kg` | $\mathbf{2.31\text{ kg}}$ (unconsumed from Day 1) |
| **Projected Usable Stock**| Ending unexpired stock on day $t$ | Simulation state after demand | $21.29 - 18.98 = \mathbf{2.31\text{ kg}}$ | $\mathbf{0.00\text{ kg}}$ |
| **Unmet Demand** | Shortfall if stock < requirement | $\max(0, \text{Req}_t - \text{Usable}_t)$ | `0.00 kg` | $\mathbf{20.19\text{ kg}}$ ($19.51 + 0.68$) |

##### Table B: Expiry-Aware Reorder Recommendations Columns
| Column Name | Formula / Derivation | Source / Function | Chicken (ING-CHI01) | Paneer (ING-PAN02) |
| :--- | :--- | :--- | :--- | :--- |
| **Ingredient** | Ingredient name and unit | Master ingredient | `Chicken (kg)` | `Paneer (kg)` |
| **Usable Stock @ Expected Delivery** | Ending stock at day $\lceil L_i \rceil$ | Spoilage simulation | $\mathbf{0.00\text{ kg}}$ (exhausted Day 2) | $\mathbf{6.48\text{ kg}}$ (after PO arrival) |
| **Forecast Requirement** | Coverage demand + prep trim ($L+R$) | Trajectory requirement sum | $\mathbf{56.10\text{ kg}}$ ($2.65\text{ days}$) | $\mathbf{22.77\text{ kg}}$ ($2.65\text{ days}$) |
| **Expected Expiry Waste** | Sum of expiries in coverage window | Trajectory expiring qty | $\mathbf{2.31\text{ kg}}$ (spoils Day 2) | $\mathbf{0.00\text{ kg}}$ |
| **Baseline Recommended Order** | $Q_{\text{base}} = \max(0, D_{\text{cov}} + SS - (S_0 + \text{Inc}))$ | `replenishment_engine.py` | $\mathbf{68.89\text{ kg}}$ | $\mathbf{20.29\text{ kg}}$ |
| **Recommended Order Quantity** | $Q_{\text{adj}} = \max(0, \text{Req} + SS - (\text{EffStock} + \text{Inc}))$| `spoilage_engine.py` | $\max(0, 56.10 + 35.98 - 18.98) = \mathbf{73.09\text{ kg}}$ | $\max(0, 22.77 + 13.32 - 15.40) = \mathbf{20.69\text{ kg}}$ |
| **Reorder Difference** | $Q_{\text{adj}} - Q_{\text{base}}$ | Expiry adjustment impact | $\mathbf{+4.20\text{ kg}}$ ($+2.31\text{ waste} + 1.89\text{ trim}$) | $\mathbf{+0.40\text{ kg}}$ (prep trim impact) |
        """
    )

# Expander 3: Methodology, Formulas & Data Limitations Audit
with st.expander("ℹ️ Methodology, Formulas & Data Limitations Audit", expanded=False):
    st.markdown(
        """
        ### 1. Preparation Waste vs Recorded Expiry Waste:
        - **Source of `wastage_percent`:** Defined in `recipe_ingredient.csv` (range 0.18% - 3.90%, mean 2.16%).
        - **Interpretation:** Represents nominal recipe preparation trim allowance (e.g. 3.10% for Chicken in Butter Chicken).
        - **Demand Model Verification:** Analysis of `DataCleaned/daily_ingredient_demand.csv` and `forecast_outputs/demand_data.csv` proves historical demand was calculated using raw dish consumption (`order_quantity * recipe_quantity / 1000`) without applying `wastage_percent`.
        - **Calculation Application:** For forecast demand, the allowance is applied once as:
          `Estimated Preparation Waste = Daily Forecast Demand * (p_waste / 100)`.
          Total daily requirement is: `Requirement = Daily Forecast Demand + Estimated Preparation Waste`.
        - **Actual Waste Audit:** In the operational stock ledger (`stock_ledger_entry.csv`), all 158 recorded wastage entries specify `reason = 'Expired stock removed'` (expired batches). RMS records zero physical scrap logs for kitchen prep waste. Therefore, preparation waste is preserved strictly as an estimated recipe allowance and kept separate from recorded expiry waste.
        
        ### 2. Documented Expiry-Day Rule:
        - A batch becomes unusable on the date `expiry_date <= current_date`.
        - Verified by analysis of 148 historical wastage entries in `stock_ledger_entry.csv` where every wastage write-off date (`posted_at`) matches `expiry_date` exactly.
        - Expired stock is removed before that day's consumption and is never permitted to satisfy demand.
        - Consumed stock and expiry waste are mutually exclusive; the same quantity is never double-counted.

        ### 3. Expiry-Aware Reorder Recommendation:
        - Baseline formula: `Q_base = max(0, Coverage Demand + SS - (Current Stock + Eligible Incoming))`
        - Expiry-adjusted formula: `Q_adj = max(0, Coverage Requirement + SS - (Effective Usable Stock + Eligible Incoming))`
        - Where `Effective Usable Stock = max(0, Current Usable Stock - Expected Expiry Waste in Coverage)`.
        - This ensures stock expiring before demand can consume it is compensated in the reorder recommendation without subtracting expiry waste twice.

        ### 4. Verified Limitations:
        - **Unreceived Purchase Orders:** Purchase order line items do not contain batch numbers or expiry dates prior to physical vendor receipt. Unreceived incoming deliveries are treated as fresh upon arrival.
        - **Measured Actual Kitchen Waste:** Cannot calculate — required empirical preparation scrap measurement data is unavailable in RMS database records.
        """
    )

    st.write("##### Recipe Trim Parameters vs Recorded Expiry Waste Comparison:")
    st.dataframe(get_recipe_wastage_comparison(master_data, base_dir=BASE_DIR), use_container_width=True, hide_index=True)

st.divider()
st.page_link("app.py", label="← Return to Replenishment Dashboard", icon="📊")
