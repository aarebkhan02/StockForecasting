import math
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

# Replenishment Engine functions
from replenishment_engine import (
    load_master_datasets,
    generate_holt_winters_forecasts,
    compute_all_replenishment_metrics,
)

# UI & Theme styling
import importlib
import ui_theme
importlib.reload(ui_theme)
from ui_theme import (
    inject_custom_css,
    style_risk_cell,
    style_buffer_cell,
    apply_plotly_theme,
)

# -----------------------------
# 0. Page Configuration & Setup
# -----------------------------
st.set_page_config(
    page_title="Restaurant Inventory Forecasting & Replenishment",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject modern UI styling
inject_custom_css()

# Paths relative to project directory
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data-rms" / "data-rms"

# Load restaurant master data for order system
menu_items = pd.read_csv(DATA_DIR / "menu_item.csv")
ingredients = pd.read_csv(DATA_DIR / "ingredient.csv")
recipes = pd.read_csv(DATA_DIR / "recipe.csv")
recipe_versions = pd.read_csv(DATA_DIR / "recipe_version.csv")
recipe_ingredients = pd.read_csv(DATA_DIR / "recipe_ingredient.csv")
stock = pd.read_csv(DATA_DIR / "stock_balance.csv")
uom = pd.read_csv(DATA_DIR / "unit_of_measure.csv")
uom_conversions = pd.read_csv(DATA_DIR / "uom_conversion.csv")

# Load master datasets for forecasting, lead-time and procurement
master_data = load_master_datasets(BASE_DIR)


def convert_to_base_unit(qty, from_uom_id, to_uom_id, conversions_df):
    """
    Convert a quantity from a source unit (from_uom_id) to a base unit (to_uom_id).
    
    Handles:
    - Same unit: factor = 1.0.
    - Direct conversion: factor defined from -> to in conversions_df.
    - Reverse conversion: factor defined to -> from (1 / factor).
    - Unsupported conversion: returns None.
    """
    if from_uom_id == to_uom_id:
        return qty

    # 1. Direct conversion
    direct = conversions_df[
        (conversions_df["from_uom_id"] == from_uom_id) &
        (conversions_df["to_uom_id"] == to_uom_id)
    ]
    if not direct.empty:
        factor = direct.iloc[0]["factor"]
        return qty * factor

    # 2. Reverse conversion
    reverse = conversions_df[
        (conversions_df["from_uom_id"] == to_uom_id) &
        (conversions_df["to_uom_id"] == from_uom_id)
    ]
    if not reverse.empty:
        factor = reverse.iloc[0]["factor"]
        if factor != 0:
            return qty / factor

    return None


# -----------------------------
# 1. In-Memory Simulated Inventory Session State
# -----------------------------
# Original CSV files remain untouched; demo changes are held in Streamlit session state
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

if "selected_kpi" not in st.session_state:
    st.session_state.selected_kpi = None


# -----------------------------
# 2. Sidebar Configuration Controls
# -----------------------------
with st.sidebar:
    st.markdown("### 🧭 Navigation")
    st.page_link("app.py", label="Replenishment Dashboard", icon="📊")
    st.page_link("pages/1_Place_Customer_Order.py", label="Place Customer Order", icon="🛒")
    st.divider()

    st.markdown("### ⚙️ Replenishment Controls")
    st.caption("Configurable inventory and risk policy parameters.")

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
        help="One-sided normal approximation factor. Assumes demand and lead-time variance are independent."
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
        help="Time between inventory review opportunities. Order recommendations cover forecast demand over (Lead Time + R) days."
    )
    st.caption(f"Active Review Period: **R = {review_period:.1f} days**")

    # Risk-Assessment Horizon control
    st.subheader("3. Risk Horizon (H)")
    risk_horizon = st.slider(
        "Risk Assessment Horizon H (Days)",
        min_value=3,
        max_value=14,
        value=7,
        step=1,
        help="Window in days over which projected stockouts and safety stock breaches are flagged."
    )
    st.caption(f"Active Risk Horizon: **H = {risk_horizon} days**")

    st.divider()

    # Inventory Session Control
    st.subheader("🔄 Operational Stock Control")
    st.caption("Current inventory operates on in-memory simulated stock. Original CSV files remain untouched.")
    if st.button("Reset Demo Inventory", type="secondary", use_container_width=True):
        st.session_state.simulated_stock = stock.copy()
        st.session_state.order_confirmed_msg = None
        st.session_state.last_deduction_summary = None
        st.session_state.confirmed_order_key = None
        st.session_state.selected_kpi = None
        st.success("Simulated stock restored to original starting balance.")
        st.rerun()

    st.divider()
    st.markdown(
        """
        <div class="rms-meta-card">
            <div style="font-weight:700; color:#0f172a; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
                <span>📋</span> Snapshot Metadata
            </div>
            <div>• <b>Historical Data End:</b> 2026-09-22</div>
            <div>• <b>Forecast Horizon:</b> Next 7 Days (2026-09-23 to 2026-09-29)</div>
            <div>• <b>Forecast Model:</b> Holt-Winters Additive Seasonality (<code>seasonal_periods=7</code>)</div>
            <div>• <b>Lead Time Source:</b> <code>full_lead_time_summary.csv</code></div>
        </div>
        """,
        unsafe_allow_html=True
    )


# -----------------------------
# 3. Dynamic Calculation Engine
# -----------------------------
# Generate 7-day Holt-Winters forecasts (cached; only reruns if historical data changes)
forecast_results = generate_holt_winters_forecasts(
    master_data["demand_df"],
    horizon=7
)

# Compute replenishment metrics using live simulated stock (recalculates whenever orders deduct stock)
replenishment_metrics = compute_all_replenishment_metrics(
    st.session_state.simulated_stock,
    master_data,
    forecast_results,
    z_score=z_score,
    review_period=review_period,
    risk_horizon=risk_horizon,
)

summary_df = replenishment_metrics["summary_df"]
forecast_dates = replenishment_metrics["forecast_dates"]
forecast_date_range_str = f"{forecast_dates[0]:%Y-%m-%d} to {forecast_dates[-1]:%Y-%m-%d}"


# -----------------------------
# 4. Top Header & Status
# -----------------------------
st.markdown(
    f"""
    <div class="rms-hero-card rms-hero-dashboard" style="position:relative; overflow:hidden; background:radial-gradient(circle at 92% 10%, rgba(99, 102, 241, 0.09) 0%, transparent 45%), radial-gradient(circle at 8% 85%, rgba(14, 165, 233, 0.07) 0%, transparent 40%), #ffffff !important; border:1px solid #e2e8f0 !important; border-top:3.5px solid #2563eb !important; color:#0f172a !important; padding:1.35rem 1.75rem !important; border-radius:16px !important; box-shadow:0 4px 20px -2px rgba(99, 102, 241, 0.08), 0 2px 6px -1px rgba(15, 23, 42, 0.03) !important; margin-bottom:1.5rem !important;">
        <div style="display:flex; align-items:center; gap:0.85rem;">
            <div>
                <h1 class="rms-hero-title" style="color:#0f172a !important; font-size:1.45rem !important; font-weight:800 !important; margin:0 !important; font-family:'Plus Jakarta Sans', sans-serif !important; letter-spacing:-0.025em !important;">
                    Restaurant Inventory Forecasting &amp; Replenishment Dashboard
                </h1>
                <div class="rms-hero-subtitle" style="color:#475569 !important; font-size:0.9rem !important; margin:0.4rem 0 0 0 !important; line-height:1.5 !important;">
                    Weekly Holt-Winters demand forecasts, dynamic safety stock, and automated replenishment.
                </div>
            </div>
        </div>
        <div class="rms-badge-group" style="margin-top:0.75rem !important; display:flex !important; flex-wrap:wrap !important; gap:0.55rem !important;">
            <span class="rms-pill rms-pill-model" style="background:linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important; color:#047857 !important; border:1px solid #6ee7b7 !important; box-shadow:0 2px 6px rgba(16, 185, 129, 0.15) !important; font-weight:700 !important;">📈 Holt-Winters (7d Horizon)</span>
            <span class="rms-pill rms-pill-date" style="background:linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%) !important; color:#b45309 !important; border:1px solid #fcd34d !important; box-shadow:0 2px 6px rgba(245, 158, 11, 0.15) !important; font-weight:700 !important;">📅 Snapshot: 2026-09-22</span>
            <span class="rms-pill rms-pill-info" style="background:linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%) !important; color:#1d4ed8 !important; border:1px solid #93c5fd !important; box-shadow:0 2px 6px rgba(37, 99, 235, 0.15) !important; font-weight:700 !important;">🗓️ Window: {forecast_date_range_str}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Display order confirmation notifications
if st.session_state.order_confirmed_msg:
    st.success(st.session_state.order_confirmed_msg)
    if st.session_state.last_deduction_summary:
        with st.expander("View Order Stock Deduction Details", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.last_deduction_summary), use_container_width=True)


# -----------------------------
# 5. Section A: Inventory Overview KPIs
# -----------------------------
st.markdown("---")
st.markdown(
    """
    <div class="rms-section-header">
        <span class="rms-section-number">1</span>
        <h3 class="rms-section-title">Inventory Overview</h3>
    </div>
    <div class="rms-section-desc">Live aggregate status calculated dynamically from simulated operational inventory.</div>
    """,
    unsafe_allow_html=True
)

kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)

with kpi_col1:
    is_all_active = (st.session_state.selected_kpi is None)
    with st.container(border=True):
        st.markdown('<span class="kpi-col-marker kpi-col-1"></span>', unsafe_allow_html=True)
        st.metric(
            label="Tracked Ingredients",
            value=replenishment_metrics["total_ingredients_tracked"],
            help="Total number of active kitchen ingredients tracked in the inventory master."
        )
        if st.button("All Items", key="btn_kpi_all", use_container_width=True, type="secondary"):
            st.session_state.selected_kpi = None
            st.rerun()

with kpi_col2:
    is_crit_active = (st.session_state.selected_kpi == "Critical")
    crit_marker = '<span class="kpi-col-marker kpi-col-2 kpi-active-marker"></span>' if is_crit_active else '<span class="kpi-col-marker kpi-col-2"></span>'
    with st.container(border=True):
        st.markdown(crit_marker, unsafe_allow_html=True)
        st.metric(
            label="🚨 Critical",
            value=replenishment_metrics["critical_count"],
            help="Projected stockout occurs on or before average full-delivery lead time. Stockout occurs before replenishment could arrive."
        )
        crit_label = "✓ Active Filter" if is_crit_active else f"Inspect {replenishment_metrics['critical_count']} Critical ▾"
        if st.button(crit_label, key="btn_kpi_critical", use_container_width=True, type="primary" if is_crit_active else "secondary"):
            st.session_state.selected_kpi = None if is_crit_active else "Critical"
            st.rerun()

with kpi_col3:
    is_risk_active = (st.session_state.selected_kpi == "At Risk")
    risk_marker = '<span class="kpi-col-marker kpi-col-3 kpi-active-marker"></span>' if is_risk_active else '<span class="kpi-col-marker kpi-col-3"></span>'
    with st.container(border=True):
        st.markdown(risk_marker, unsafe_allow_html=True)
        st.metric(
            label="⚠️ At Risk",
            value=replenishment_metrics["at_risk_count"],
            help="Stockout projected within risk horizon H OR projected stock at expected delivery day falls below required safety stock."
        )
        risk_label = "✓ Active Filter" if is_risk_active else f"Inspect {replenishment_metrics['at_risk_count']} At Risk ▾"
        if st.button(risk_label, key="btn_kpi_atrisk", use_container_width=True, type="primary" if is_risk_active else "secondary"):
            st.session_state.selected_kpi = None if is_risk_active else "At Risk"
            st.rerun()

with kpi_col4:
    is_suff_active = (st.session_state.selected_kpi == "Sufficient")
    suff_marker = '<span class="kpi-col-marker kpi-col-4 kpi-active-marker"></span>' if is_suff_active else '<span class="kpi-col-marker kpi-col-4"></span>'
    with st.container(border=True):
        st.markdown(suff_marker, unsafe_allow_html=True)
        st.metric(
            label="✅ Sufficient",
            value=replenishment_metrics["sufficient_count"],
            help="Projected stock and safety buffer remain adequate throughout the horizon with no stockout predicted."
        )
        suff_label = "✓ Active Filter" if is_suff_active else f"Inspect {replenishment_metrics['sufficient_count']} Sufficient ▾"
        if st.button(suff_label, key="btn_kpi_sufficient", use_container_width=True, type="primary" if is_suff_active else "secondary"):
            st.session_state.selected_kpi = None if is_suff_active else "Sufficient"
            st.rerun()

with kpi_col5:
    is_repl_active = (st.session_state.selected_kpi == "Replenishment Needed")
    repl_marker = '<span class="kpi-col-marker kpi-col-5 kpi-active-marker"></span>' if is_repl_active else '<span class="kpi-col-marker kpi-col-5"></span>'
    with st.container(border=True):
        st.markdown(repl_marker, unsafe_allow_html=True)
        st.metric(
            label="📦 Replenishment Needed",
            value=replenishment_metrics["replenishment_required_count"],
            help="Number of ingredients where the replenishment policy recommends placing an immediate purchase order (Q > 0)."
        )
        repl_label = "✓ Active Filter" if is_repl_active else f"Inspect {replenishment_metrics['replenishment_required_count']} Needed ▾"
        if st.button(repl_label, key="btn_kpi_replenish", use_container_width=True, type="primary" if is_repl_active else "secondary"):
            st.session_state.selected_kpi = None if is_repl_active else "Replenishment Needed"
            st.rerun()

# Detailed category view displayed directly below the cards when a card is selected
if st.session_state.selected_kpi is not None:
    selected_category = st.session_state.selected_kpi

    if selected_category == "Critical":
        kpi_subset = summary_df[summary_df["risk_status"] == "Critical"].copy()
        desc = "Projected stockout occurs on or before average full-delivery lead time. Stockout occurs before replenishment could arrive."
    elif selected_category == "At Risk":
        kpi_subset = summary_df[summary_df["risk_status"] == "At Risk"].copy()
        desc = f"Stockout projected within risk horizon H={risk_horizon}d or projected stock at delivery falls below required safety stock."
    elif selected_category == "Sufficient":
        kpi_subset = summary_df[summary_df["risk_status"] == "Sufficient"].copy()
        desc = f"Projected stock and safety buffer remain adequate throughout the {risk_horizon}-day horizon with no stockout predicted."
    elif selected_category == "Replenishment Needed":
        kpi_subset = summary_df[summary_df["recommended_order_qty"] > 0].copy()
        desc = "Ingredients where the replenishment policy recommends placing an immediate purchase order (Recommended Q > 0)."
    else:
        kpi_subset = summary_df.copy()
        desc = "All tracked ingredients in operational inventory."

    with st.container(border=True):
        head_c1, head_c2 = st.columns([3.8, 1.2])
        with head_c1:
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:1.1rem; font-weight:700; color:#0f172a;">
                        Category Drill-Down: <span style="color:#2563eb;">{selected_category}</span>
                    </span>
                    <span class="rms-pill rms-pill-info">{len(kpi_subset)} items</span>
                </div>
                <div style="font-size:0.83rem; color:#64748b; margin-top:2px;">
                    {desc}
                </div>
                """,
                unsafe_allow_html=True
            )
        with head_c2:
            if st.button("✕ Return to Full Table", type="secondary", use_container_width=True, key="btn_return_full_table"):
                st.session_state.selected_kpi = None
                st.rerun()

        if not kpi_subset.empty:
            kpi_records = []
            for _, r in kpi_subset.iterrows():
                c_stock = float(r["current_stock"])
                req_ss = float(r["safety_stock"])
                curr_buf = float(r["current_safety_buffer"])
                so_str = f"Day {int(r['days_to_stockout'])} ({r['stockout_date']})" if pd.notna(r["days_to_stockout"]) else f"None (>{risk_horizon}d)"
                buf_stat = "Adequate" if curr_buf >= req_ss else f"Deficit (-{req_ss - curr_buf:.2f})"

                if selected_category == "Critical":
                    kpi_records.append({
                        "Ingredient": r["ingredient_name"],
                        "Unit": r["base_uom_code"],
                        "Current Stock": round(c_stock, 2),
                        "Stockout Date": so_str,
                        "Stock @ Delivery": round(float(r["stock_at_delivery"]), 2),
                        "Avg Lead Time (d)": round(float(r["lead_time_days"]), 2),
                        "Coverage Demand": round(float(r["coverage_demand"]), 2),
                        "Recommended Order (Q)": round(float(r["recommended_order_qty"]), 2),
                        "Risk Explanation": r["risk_reason"]
                    })
                elif selected_category == "At Risk":
                    kpi_records.append({
                        "Ingredient": r["ingredient_name"],
                        "Unit": r["base_uom_code"],
                        "Current Stock": round(c_stock, 2),
                        "Required Safety Stock (SS)": round(req_ss, 2),
                        "Current Safety Buffer (B)": round(curr_buf, 2),
                        "Buffer Status": buf_stat,
                        "Stockout Date": so_str,
                        "Stock @ Delivery": round(float(r["stock_at_delivery"]), 2),
                        "Recommended Order (Q)": round(float(r["recommended_order_qty"]), 2),
                        "Risk Explanation": r["risk_reason"]
                    })
                elif selected_category == "Sufficient":
                    kpi_records.append({
                        "Ingredient": r["ingredient_name"],
                        "Unit": r["base_uom_code"],
                        "Current Stock": round(c_stock, 2),
                        "Required Safety Stock (SS)": round(req_ss, 2),
                        "Current Safety Buffer (B)": round(curr_buf, 2),
                        "Buffer Status": buf_stat,
                        "Forecast Daily Demand": round(float(r["avg_forecast_daily"]), 2),
                        "Stock @ Delivery": round(float(r["stock_at_delivery"]), 2),
                        "Stockout Date": so_str,
                        "Risk Status": r["risk_status"]
                    })
                elif selected_category == "Replenishment Needed":
                    kpi_records.append({
                        "Ingredient": r["ingredient_name"],
                        "Unit": r["base_uom_code"],
                        "Recommended Order (Q)": round(float(r["recommended_order_qty"]), 2),
                        "Current Stock": round(c_stock, 2),
                        "Required Safety Stock (SS)": round(req_ss, 2),
                        "Current Safety Buffer (B)": round(curr_buf, 2),
                        "Coverage Demand": round(float(r["coverage_demand"]), 2),
                        "Stock @ Delivery": round(float(r["stock_at_delivery"]), 2),
                        "Avg Lead Time (d)": round(float(r["lead_time_days"]), 2),
                        "Risk Status": r["risk_status"],
                        "Recommendation Reason": r["risk_reason"]
                    })

            detail_kpi_df = pd.DataFrame(kpi_records)
            styled_kpi_view = detail_kpi_df.style.format(
                {col: "{:.2f}" for col in detail_kpi_df.select_dtypes(include=["float", "float64"]).columns}
            )
            if "Risk Status" in detail_kpi_df.columns:
                styled_kpi_view = styled_kpi_view.map(style_risk_cell, subset=["Risk Status"])
            if "Buffer Status" in detail_kpi_df.columns:
                styled_kpi_view = styled_kpi_view.map(style_buffer_cell, subset=["Buffer Status"])

            st.dataframe(styled_kpi_view, use_container_width=True, height=min(320, 50 + len(kpi_records) * 36))
        else:
            st.info(f"No ingredients currently classified as {selected_category}.")

if replenishment_metrics["unknown_count"] > 0:
    st.warning(f"⚠️ {replenishment_metrics['unknown_count']} ingredients have missing or insufficient data.")


# -----------------------------
# 6. Section B: Current Inventory & Replenishment Table
# -----------------------------
st.markdown("---")
st.markdown(
    """
    <div class="rms-section-header">
        <span class="rms-section-number">2</span>
        <h3 class="rms-section-title">Inventory Status & Replenishment Recommendations</h3>
    </div>
    <div class="rms-section-desc">Comprehensive inventory metrics showing verified current stock, required safety stock targets, current safety buffers, stockout projections, and policy-driven order quantities.</div>
    """,
    unsafe_allow_html=True
)

# Search and filter bar in clean container card
with st.container(border=True):
    filter_c1, filter_c2, filter_c3 = st.columns([2.2, 2.2, 2])
    with filter_c1:
        search_text = st.text_input("🔍 Search Ingredient", "", placeholder="e.g. Chicken, Paneer...")
    with filter_c2:
        risk_filter = st.multiselect(
            "Filter Risk Status",
            options=["Critical", "At Risk", "Sufficient", "Unknown"],
            default=["Critical", "At Risk", "Sufficient", "Unknown"]
        )
    with filter_c3:
        reorder_filter = st.selectbox(
            "Filter Replenishment Need",
            options=["All Ingredients", "Replenishment Required Only (Q > 0)", "Sufficient Only (Q = 0)"],
            index=0
        )

# Filter dataframe
filtered_df = summary_df.copy()

if search_text:
    filtered_df = filtered_df[filtered_df["ingredient_name"].str.contains(search_text, case=False, na=False)]

if risk_filter:
    filtered_df = filtered_df[filtered_df["risk_status"].isin(risk_filter)]

if reorder_filter == "Replenishment Required Only (Q > 0)":
    filtered_df = filtered_df[filtered_df["recommended_order_qty"] > 0]
elif reorder_filter == "Sufficient Only (Q = 0)":
    filtered_df = filtered_df[filtered_df["recommended_order_qty"] == 0]

# Build display table with explicit required columns
display_records = []
for _, r in filtered_df.iterrows():
    c_stock = float(r["current_stock"])
    req_ss = float(r["safety_stock"])
    curr_buf = float(r["current_safety_buffer"])
    so_str = f"Day {int(r['days_to_stockout'])} ({r['stockout_date']})" if pd.notna(r["days_to_stockout"]) else f"None (>{risk_horizon}d)"

    display_records.append({
        "Ingredient": r["ingredient_name"],
        "Unit": r["base_uom_code"],
        "Current Stock": round(c_stock, 2),
        "Required Safety Stock (SS)": round(req_ss, 2),
        "Current Safety Buffer (B)": round(curr_buf, 2),
        "Buffer Status": "Adequate" if curr_buf >= req_ss else f"Deficit (-{req_ss - curr_buf:.2f})",
        "Forecast Daily Demand": round(float(r["avg_forecast_daily"]), 2),
        "Avg Lead Time (d)": round(float(r["lead_time_days"]), 2),
        "Coverage Demand": round(float(r["coverage_demand"]), 2),
        "Stock @ Delivery": round(float(r["stock_at_delivery"]), 2),
        "Stockout Date": so_str,
        "Risk Status": r["risk_status"],
        "Recommended Order (Q)": round(float(r["recommended_order_qty"]), 2),
        "Recommendation Reason": r["risk_reason"],
        "Data Confidence": r["lead_time_uncertainty"]
    })

display_df = pd.DataFrame(display_records)

if not display_df.empty:
    styled_view = (
        display_df.style
        .format({
            "Current Stock": "{:.2f}",
            "Required Safety Stock (SS)": "{:.2f}",
            "Current Safety Buffer (B)": "{:.2f}",
            "Forecast Daily Demand": "{:.2f}",
            "Avg Lead Time (d)": "{:.2f}",
            "Coverage Demand": "{:.2f}",
            "Stock @ Delivery": "{:.2f}",
            "Recommended Order (Q)": "{:.2f}",
        })
        .map(style_risk_cell, subset=["Risk Status"])
        .map(style_buffer_cell, subset=["Buffer Status"])
    )
    st.dataframe(styled_view, use_container_width=True, height=430)
else:
    st.info("No ingredients match the selected filters.")


# -----------------------------
# 7. Section C: Analysis & Chart Deep-Dive
# -----------------------------
st.markdown("---")
st.markdown(
    """
    <div class="rms-section-header">
        <span class="rms-section-number">3</span>
        <h3 class="rms-section-title">Ingredient Forecast & Stock Trajectory Analysis</h3>
    </div>
    <div class="rms-section-desc">Select an ingredient to inspect daily demand predictions, inventory projection trajectory, and safety buffer adequacy.</div>
    """,
    unsafe_allow_html=True
)

selected_ing_name = st.selectbox(
    "Select Ingredient for Deep-Dive:",
    options=summary_df["ingredient_name"].tolist(),
    index=0
)

# Retrieve data for selected ingredient
ing_data = summary_df[summary_df["ingredient_name"] == selected_ing_name].iloc[0]
sel_id = int(ing_data["ingredient_id"])
sel_unit = ing_data["base_uom_code"]
sel_current_stock = float(ing_data["current_stock"])
sel_safety_stock = float(ing_data["safety_stock"])
sel_safety_buffer = float(ing_data["current_safety_buffer"])
sel_recom_qty = float(ing_data["recommended_order_qty"])
sel_lead_time = float(ing_data["lead_time_days"])

traj_dict = replenishment_metrics["trajectories"][sel_id]
traj_table = traj_dict["trajectory_df"]

chart_c1, chart_c2 = st.columns(2)

with chart_c1:
    st.markdown(
        f"""
        <div class="rms-chart-title">
            <span>📈</span> 7-Day Demand Forecast: <span style="color:#2563eb;">{selected_ing_name}</span>
        </div>
        <div class="rms-chart-subtitle">Historical daily consumption vs Holt-Winters additive seasonal model.</div>
        """,
        unsafe_allow_html=True
    )
    hist_sub = master_data["demand_df"][master_data["demand_df"]["ingredient_id"] == sel_id].sort_values("date")
    f_series = forecast_results["forecasts"][sel_id]

    fig_demand = go.Figure()
    # Last 45 days historical demand
    recent_hist = hist_sub.tail(45)
    fig_demand.add_trace(go.Scatter(
        x=recent_hist["date"],
        y=recent_hist["daily_demand"],
        mode="lines",
        name="Historical Daily Demand",
        line=dict(color="#64748b", width=1.75),
        fill="tozeroy",
        fillcolor="rgba(100, 116, 139, 0.06)",
        hovertemplate="<b>Date</b>: %{x}<br><b>Historical Demand</b>: %{y:.2f} " + sel_unit + "<extra></extra>"
    ))
    fig_demand.add_trace(go.Scatter(
        x=f_series.index,
        y=f_series.values,
        mode="lines+markers",
        name="Holt-Winters 7-Day Forecast",
        line=dict(color="#f97316", width=2.75),
        marker=dict(size=7, color="#ea580c", line=dict(color="#ffffff", width=1.5)),
        hovertemplate="<b>Date</b>: %{x}<br><b>Forecast Demand</b>: %{y:.2f} " + sel_unit + "<extra></extra>"
    ))
    fig_demand.update_layout(
        xaxis_title="Date",
        yaxis_title=f"Demand ({sel_unit}/day)"
    )
    apply_plotly_theme(fig_demand, height=390)
    st.plotly_chart(fig_demand, use_container_width=True)

with chart_c2:
    st.markdown(
        f"""
        <div class="rms-chart-title">
            <span>📉</span> Projected Inventory Trajectory: <span style="color:#2563eb;">{selected_ing_name}</span>
        </div>
        <div class="rms-chart-subtitle">Stock depletion simulation vs safety stock threshold and verified PO arrivals.</div>
        """,
        unsafe_allow_html=True
    )
    traj_x = ["Day 0 (Snapshot)"] + [f"Day {row['day']} ({row['date_str']})" for _, row in traj_table.iterrows()]
    traj_y = [sel_current_stock] + traj_table["projected_unconstrained"].tolist()

    fig_traj = go.Figure()
    # Projected inventory line
    fig_traj.add_trace(go.Scatter(
        x=traj_x,
        y=traj_y,
        mode="lines+markers",
        name="Projected Inventory",
        line=dict(color="#2563eb", width=2.75),
        marker=dict(size=6, color="#1d4ed8", line=dict(color="#ffffff", width=1.5)),
        hovertemplate="<b>Timeline</b>: %{x}<br><b>Projected Stock</b>: %{y:.2f} " + sel_unit + "<extra></extra>"
    ))
    # Required Safety Stock threshold
    fig_traj.add_trace(go.Scatter(
        x=traj_x,
        y=[sel_safety_stock] * len(traj_x),
        mode="lines",
        name="Required Safety Stock (SS)",
        line=dict(color="#dc2626", width=2, dash="dash"),
        hovertemplate="<b>Required SS</b>: %{y:.2f} " + sel_unit + "<extra></extra>"
    ))
    # Zero stockout boundary
    fig_traj.add_trace(go.Scatter(
        x=traj_x,
        y=[0.0] * len(traj_x),
        mode="lines",
        name="Zero Boundary",
        line=dict(color="#94a3b8", width=1.5, dash="dot"),
        hoverinfo="skip"
    ))

    # Mark verified incoming deliveries
    for _, row in traj_table.iterrows():
        if row["confirmed_receipts"] > 0:
            fig_traj.add_annotation(
                x=f"Day {row['day']} ({row['date_str']})",
                y=row["projected_unconstrained"],
                text=f"📦 +{row['confirmed_receipts']:.1f} {sel_unit}",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#059669",
                bgcolor="#f0fdf4",
                bordercolor="#059669",
                font=dict(color="#047857", size=10, family="Inter, sans-serif")
            )

    fig_traj.update_layout(
        xaxis_title="Timeline",
        yaxis_title=f"Stock ({sel_unit})"
    )
    apply_plotly_theme(fig_traj, height=390)
    st.plotly_chart(fig_traj, use_container_width=True)


# -----------------------------
# 8. Section D: Historical Lead-Time Statistics
# -----------------------------
st.markdown(f"#### 🚚 Historical Lead-Time Statistics: **{selected_ing_name}**")
st.caption("Derived from actual delivery history in `lead_time_outputs/full_lead_time_summary.csv`.")
lt_c1, lt_c2, lt_c3, lt_c4 = st.columns(4)
with lt_c1:
    st.metric("Average Full Lead Time", f"{ing_data['lead_time_days']:.2f} days")
with lt_c2:
    st.metric("Median Full Lead Time", f"{ing_data['median_lead_time_days']:.2f} days")
with lt_c3:
    st.metric("Lead-Time Variance (σ²_L)", f"{ing_data['lead_time_variance']:.3f}")
with lt_c4:
    st.metric("Completed Deliveries Sample", f"{int(ing_data['full_deliveries'])} orders")

st.info(f"📊 **Data Confidence Assessment:** **{ing_data['lead_time_uncertainty']}** based on {int(ing_data['full_deliveries'])} verified full deliveries.")


# -----------------------------
# 9. Section E: Verified Inbound Procurement Orders
# -----------------------------
st.markdown("---")
st.markdown(
    """
    <div class="rms-section-header">
        <span class="rms-section-number">4</span>
        <h3 class="rms-section-title">Verified Inbound Procurement Orders</h3>
    </div>
    <div class="rms-section-desc">Active purchase orders verified in <code>purchase_order.csv</code> and <code>purchase_order_item.csv</code>. Credit is applied to projected stock strictly on the recorded expected arrival date.</div>
    """,
    unsafe_allow_html=True
)

all_po_df = replenishment_metrics["all_procurement_df"]

if not all_po_df.empty:
    po_display = all_po_df.rename(columns={
        "po_number": "PO Number",
        "ingredient_name": "Ingredient",
        "unit_code": "Unit",
        "quantity": "Total Ordered",
        "received_qty": "Accepted Received",
        "pending_qty": "Outstanding Pending",
        "expected_date": "Expected Date",
        "state": "PO State",
        "delivery_status": "Fulfillment Status"
    })
    po_display["Expected Date"] = pd.to_datetime(po_display["Expected Date"]).dt.strftime("%Y-%m-%d")
    
    # Format float values
    po_styled = po_display[[
        "PO Number", "Ingredient", "Unit", "Total Ordered",
        "Accepted Received", "Outstanding Pending", "Expected Date",
        "PO State", "Fulfillment Status"
    ]].style.format({
        "Total Ordered": "{:.2f}",
        "Accepted Received": "{:.2f}",
        "Outstanding Pending": "{:.2f}"
    })

    st.dataframe(
        po_styled,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No active or pending purchase orders found in procurement records.")


# -----------------------------
# 10. Bottom Navigation Banner
# -----------------------------
st.markdown("---")
c_link1, c_link2 = st.columns([3, 1])

with c_link2:
    st.page_link("pages/1_Place_Customer_Order.py")
