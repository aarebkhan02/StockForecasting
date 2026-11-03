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
    st.page_link("pages/2_Spoilage_Forecasting.py", label="Spoilage Forecasting", icon="🥀")
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
    <div class="rms-hero-card rms-hero-dashboard" style="position:relative; overflow:hidden; background:radial-gradient(circle at 92% 10%, rgba(99, 102, 241, 0.09) 0%, transparent 45%), radial-gradient(circle at 8% 85%, rgba(14, 165, 233, 0.07) 0%, transparent 40%), #ffffff !important; border:none !important; color:#0f172a !important; padding:1.35rem 1.75rem !important; border-radius:16px !important; box-shadow:0 4px 20px -2px rgba(99, 102, 241, 0.08), 0 2px 6px -1px rgba(15, 23, 42, 0.03) !important; margin-bottom:1.5rem !important;">
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
            <span class="rms-pill rms-pill-model" style="background:linear-gradient(135deg, #dcfce7 0%, #86efac 100%) !important; color:#14532d !important; border:none !important; box-shadow:0 2px 8px rgba(34, 197, 94, 0.25) !important; font-weight:700 !important;">📈 Holt-Winters (7d Horizon)</span>
            <span class="rms-pill rms-pill-date" style="background:linear-gradient(135deg, #fef3c7 0%, #fde68a 100%) !important; color:#78350f !important; border:none !important; box-shadow:0 2px 8px rgba(245, 158, 11, 0.25) !important; font-weight:700 !important;">📅 Snapshot: 2026-09-22</span>
            <span class="rms-pill rms-pill-info" style="background:linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%) !important; color:#1d4ed8 !important; border:none !important; box-shadow:0 2px 6px rgba(37, 99, 235, 0.15) !important; font-weight:700 !important;">🗓️ Window: {forecast_date_range_str}</span>
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
# 10. Section F: Complete Calculation & Formula Explanations
# -----------------------------
st.markdown("---")
with st.expander("📐 How are these values calculated? (Complete Formula & Calculation Guide)", expanded=False):
    st.markdown(
        r"""
### 🧭 Complete Stockout Forecasting & Replenishment Calculation Guide

This guide details the mathematical foundations, data sources, Python functions, and exact derivation steps for every metric, column, and recommendation displayed in this dashboard.

---

#### 1. Data Sources & Pipeline Architecture
The values in this dashboard originate from raw operational datasets and undergo systematic preprocessing:
- **Historical Sales Demand:** Extracted from `order.csv` (26,919 orders) and `order_item.csv` (49,683 items), linked through active recipes (`recipe.csv`, `recipe_version.csv`, `recipe_ingredient.csv`) and normalized to base units via `uom_conversion.csv`. Grouped daily to produce `DataCleaned/daily_ingredient_demand.csv`.
- **Current Physical Inventory ($S_{i,0}$):** Sourced from `data-rms/data-rms/stock_balance.csv` (`qty_base`). Held in Streamlit `st.session_state.simulated_stock` so demo order deductions operate atomically in memory without mutating raw files.
- **Supplier Lead Times ($L_i, \sigma_{L,i}^2$):** Derived in `lead_time.ipynb` and stored in `lead_time_outputs/full_lead_time_summary.csv`. Tracks calendar days until cumulative accepted receipts reached 100% of purchase order quantities.
- **Active Inbound Orders ($\text{Incoming}_i$):** Extracted from `purchase_order.csv` and `purchase_order_item.csv` (state `'APPROVED'` with pending quantities).

---

#### 2. Demand Forecasting (`generate_holt_winters_forecasts` in `replenishment_engine.py`)
- **Daily Continuity & Interpolation:** Daily series are converted to explicit calendar frequency (`.asfreq('D')`). Any missing intermediate dates are linearly interpolated (`series.interpolate(method='linear')`).
- **Algorithm:** Additive Holt-Winters Exponential Smoothing (`statsmodels.tsa.holtwinters.ExponentialSmoothing`):
  $$\hat{D}_{i,t} = \ell_{i,t-1} + b_{i,t-1} + s_{i,t-m}$$
  Where trend is additive (`trend="add"`), weekly seasonality is additive (`seasonal="add"`), and period $m = 7$ days.
- **Negative Forecast Clipping:** Raw model forecasts are clipped to non-negative values:
  $$\hat{D}_{i,t} = \max\left(0.0, \hat{D}_{\text{raw}, i, t}\right)$$
- **Historical Mean Fallback:** If numerical optimization fails on sparse data, the engine automatically falls back to historical average daily demand: $\hat{D}_{i,t} = \max\left(0.0, \bar{D}_{i, \text{hist}}\right)$.
- **Forecast Daily Demand (Displayed):** Simple arithmetic mean of daily predictions across horizon $H$:
  $$\text{Forecast Daily Demand} = \frac{1}{H} \sum_{t=1}^H \hat{D}_{i,t}$$

---

#### 3. Dynamic Safety Stock ($SS_i$) (`calculate_dynamic_safety_stock` in `replenishment_engine.py`)
Safety stock protects against both volatile customer orders and unpredictable supplier deliveries using the dual-uncertainty formula:
$$SS_i = z \times \sqrt{L_i \cdot \sigma_{D,i}^2 + \hat{D}_{\text{mean}, i}^2 \cdot \sigma_{L,i}^2}$$

Where:
- $z$: Service level factor (default $1.645$ for nominal 95% one-sided normal cycle service level; configurable $1.282$ for 90%, $2.326$ for 99%).
- $L_i$: Average full-delivery lead time in calendar days (`avg_full_lead_time_days` from `full_lead_time_summary.csv`).
- $\sigma_{D,i}^2$: Historical daily demand sample variance (`series.var()`).
- $\hat{D}_{\text{mean}, i}$: Mean forecast daily demand over the replenishment coverage window.
- $\sigma_{L,i}^2$: Full-delivery lead-time sample variance (`full_lead_time_variance`).
- **Demand Uncertainty Component:** $L_i \cdot \sigma_{D,i}^2$ represents demand variation accumulating over the duration of lead time.
- **Lead-Time Uncertainty Component:** $\hat{D}_{\text{mean}, i}^2 \cdot \sigma_{L,i}^2$ represents inventory risk when vendor shipments are delayed.

---

#### 4. Current Safety Buffer ($B_i$) (`calculate_safety_buffer` in `replenishment_engine.py`)
Measures the verified stock remaining after serving forecast demand during supplier lead time:
$$B_i = S_{i,0} - D_{\text{lead\_time}, i}$$
Where lead-time demand is prorated for fractional days ($d_{\text{full}} = \lfloor L_i \rfloor$, $d_{\text{frac}} = L_i - d_{\text{full}}$):
$$D_{\text{lead\_time}, i} = \sum_{t=1}^{d_{\text{full}}} \hat{D}_{i,t} + \left( d_{\text{frac}} \times \hat{D}_{i, d_{\text{full}}+1} \right)$$
- **Buffer Status:**
  - $\text{"Adequate"}$ if $B_i \ge SS_i$.
  - $\text{"Deficit"}$ if $B_i < SS_i$, displaying the shortfall amount: $\text{Deficit} = -(SS_i - B_i)$.

---

#### 5. Stock Trajectory & Stockout Date (`project_stock_trajectory` in `replenishment_engine.py`)
Simulates day-by-day unconstrained balance across forecast horizon $t \in \{1, 2, \dots, H\}$:
$$S_{i,t} = S_{i,t-1} - \hat{D}_{i,t} + \text{Incoming}_{i,t}$$
- **Incoming Crediting Rule:** Inbound PO quantities are credited **strictly on their recorded expected arrival date** (`arrivals = incoming[expected_date == f_norm]`).
- **Stockout Day ($t_{\text{stockout}}$):** The first step index $t$ where unconstrained balance $S_{i,t} \le 0.0$.
- **Stockout Date:** Calendar date corresponding to step $t_{\text{stockout}}$ ($t_{\text{latest}} + t_{\text{stockout}} \text{ days}$).
- **Stock @ Delivery:** Projected stock at delivery arrival day $\lceil L_i \rceil$: $S_{i, \lceil L_i \rceil}$.
- **Physically Available Stock:** $\max(0.0, S_{i,t})$.
- **Cumulative Shortage:** $\max(0.0, -S_{i,t})$.

---

#### 6. Stockout Risk Classification (`classify_risk` in `replenishment_engine.py`)
- **Critical:** $t_{\text{stockout}} \le L_i$. Projected stockout occurs earlier than or equal to supplier lead time. A stockout is unavoidable via normal procurement.
- **At Risk:** $t_{\text{stockout}} \le H$ (after lead time but within horizon), OR $S_{i, \lceil L_i \rceil} < SS_i$ (stock at delivery day falls below safety stock), OR $B_i < SS_i$ (safety buffer deficit).
- **Sufficient:** No stockout projected across horizon $H$, stock at delivery day $\ge SS_i$, and current buffer $\ge SS_i$.
- **Unknown:** Incomplete historical records or missing supplier lead time.

---

#### 7. Recommended Reorder Quantity ($Q_i$) (`calculate_replenishment_recommendation` in `replenishment_engine.py`)
Calculates net purchase order quantity required to cover lead time plus review period ($C_i = L_i + R$):
$$Q_{\text{raw}, i} = \max\left(0.0, D_{\text{cov}, i} + SS_i - (S_{i,0} + \text{Eligible Incoming}_i)\right)$$
$$Q_{\text{recommended}, i} = \text{round}(Q_{\text{raw}, i}, 2)$$

Where:
- $D_{\text{cov}, i}$: Prorated forecast demand over coverage window $C_i = L_i + R$:
  $$D_{\text{cov}, i} = \sum_{t=1}^{\lfloor C_i \rfloor} \hat{D}_{i,t} + (C_i - \lfloor C_i \rfloor) \times \hat{D}_{i, \lfloor C_i \rfloor + 1}$$
- $\text{Eligible Incoming}_i$: Sum of pending quantities in `'APPROVED'` POs arriving within the coverage window ($\text{expected\_date} \le t_{\text{latest}} + \lceil C_i \rceil$). Orders arriving after coverage are excluded.
- If $Q_{\text{recommended}, i} > 0 \implies \text{Reorder Required}$.

---

#### 8. Column-by-Column Derivation & Real Numerical Examples

| Displayed Column | Formula / Calculation | Inputs & Source | Example: Chicken (ING-CHI01) | Example: Paneer (ING-PAN02) | Example: Basmati Rice (ING-BAS03) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Current Stock** | $S_{i,0} = \sum \text{qty\_base}$ | `stock_balance.csv` / session state | **$21.29\text{ kg}$** | **$0.40\text{ kg}$** | **$33.77\text{ kg}$** |
| **Required Safety Stock (SS)**| $z \sqrt{L_i \sigma_D^2 + \hat{D}^2 \sigma_L^2}$ | $z=1.645$, $L_i, \sigma_L^2$ (`full_lead_time_summary`), $\sigma_D^2, \hat{D}$ | **$35.98\text{ kg}$** | **$13.32\text{ kg}$** | **$25.19\text{ kg}$** |
| **Current Safety Buffer (B)** | $S_{i,0} - D_{\text{lead\_time}}$ | Current Stock, lead-time demand | $21.29 - 31.02 = \mathbf{-9.73\text{ kg}}$ | $0.40 - 12.88 = \mathbf{-12.48\text{ kg}}$ | $33.77 - 51.59 = \mathbf{-17.82\text{ kg}}$ |
| **Buffer Status** | Adequate if $B \ge SS$, else Deficit | $B_i, SS_i$ | **Deficit ($-45.71$)** | **Deficit ($-25.80$)** | **Deficit ($-43.01$)** |
| **Forecast Daily Demand** | $\frac{1}{H}\sum_{t=1}^H \hat{D}_t$ | 7-day Holt-Winters forecast | **$22.52\text{ kg/day}$** | **$9.19\text{ kg/day}$** | **$13.02\text{ kg/day}$** |
| **Avg Lead Time (d)** | $L_i$ | `full_lead_time_summary.csv` | **$1.65\text{ days}$** | **$1.65\text{ days}$** | **$3.84\text{ days}$** |
| **Coverage Demand** | $\sum_{t=1}^{L+R} \hat{D}_t$ (prorated) | Forecast series, $L+R$ | $2.65\text{ days} \rightarrow \mathbf{54.20\text{ kg}}$ | $2.65\text{ days} \rightarrow \mathbf{22.37\text{ kg}}$ | $4.84\text{ days} \rightarrow \mathbf{68.31\text{ kg}}$ |
| **Stock @ Delivery** | Projected stock on day $\lceil L_i \rceil$ | Trajectory at day $\lceil L_i \rceil$ | Day 2 balance: $\mathbf{-16.56\text{ kg}}$ | Day 2 balance: $\mathbf{-0.41\text{ kg}}$ | Day 4 balance: $\mathbf{54.32\text{ kg}}$ |
| **Stockout Date** | First day where balance $\le 0$ | $S_{i,t} \le 0$ | **Day 2 (2026-09-24)** | **Day 1 (2026-09-23)** | **Day 3 (2026-09-25)** |
| **Risk Status** | Critical / At Risk / Sufficient | $t_{\text{so}}, L_i, H, S_{\text{del}}, SS, B$ | **At Risk** ($t_{\text{so}} > L$, buffer deficit)| **Critical** ($t_{\text{so}} \le L$)| **Critical** ($t_{\text{so}} \le L$)|
| **Eligible Incoming** | $\sum \text{pending\_qty}$ within cov | Approved POs | **$0.00\text{ kg}$** | **$15.00\text{ kg}$** (PO-758 on Day 2)| **$75.00\text{ kg}$** (PO-759 on Day 4)|
| **Recommended Order (Q)** | $\max(0, D_{\text{cov}} + SS - (S_0 + \text{Inc}))$ | $D_{\text{cov}}, SS, S_0, \text{Incoming}$ | $\max(0, 54.20 + 35.98 - 21.29) = \mathbf{68.89\text{ kg}}$ | $\max(0, 22.37 + 13.32 - 15.40) = \mathbf{20.29\text{ kg}}$ | $\max(0, 68.31 + 25.19 - 108.77) = \mathbf{0.00\text{ kg}}$ |
| **Data Confidence** | Based on completed PO count | Deliveries $N \ge 30 \implies \text{High}$ | **High** ($N = 162$ deliveries) | **High** ($N = 121$ deliveries) | **High** ($N = 37$ deliveries) |
        """
    )


# -----------------------------
# 10. Bottom Navigation Banner
# -----------------------------
st.markdown("---")
bot_c1, bot_c2 = st.columns(2)
with bot_c1:
    st.page_link("pages/1_Place_Customer_Order.py", label="Place Customer Order", icon="🛒")
with bot_c2:
    st.page_link("pages/2_Spoilage_Forecasting.py", label="Spoilage Forecasting", icon="🥀")
