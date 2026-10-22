import streamlit as st
import pandas as pd
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data-rms" / "data-rms"

# UI & Theme styling
import sys
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import importlib
import ui_theme
importlib.reload(ui_theme)
from ui_theme import (
    inject_custom_css,
    style_availability_cell,
)

# Set page configuration
st.set_page_config(
    page_title="Place Customer Order - Restaurant RMS",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject modern UI styling
inject_custom_css()

# Load restaurant master data
menu_items = pd.read_csv(DATA_DIR / "menu_item.csv")
ingredients = pd.read_csv(DATA_DIR / "ingredient.csv")
recipes = pd.read_csv(DATA_DIR / "recipe.csv")
recipe_versions = pd.read_csv(DATA_DIR / "recipe_version.csv")
recipe_ingredients = pd.read_csv(DATA_DIR / "recipe_ingredient.csv")
stock = pd.read_csv(DATA_DIR / "stock_balance.csv")
uom = pd.read_csv(DATA_DIR / "unit_of_measure.csv")
uom_conversions = pd.read_csv(DATA_DIR / "uom_conversion.csv")


def convert_to_base_unit(qty, from_uom_id, to_uom_id, conversions_df):
    """
    Convert a quantity from a source unit (from_uom_id) to a base unit (to_uom_id).
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


# In-memory simulated stock state
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


# Sidebar
with st.sidebar:
    st.markdown("### 🧭 Navigation")
    st.page_link("app.py", label="Replenishment Dashboard", icon="📊")
    st.page_link("pages/1_Place_Customer_Order.py", label="Place Customer Order", icon="🛒")
    st.divider()

    st.markdown("### 🔄 Operational Stock Control")
    st.caption("Operational stock is maintained in memory. Reset restores original starting stock.")
    if st.button("Reset Demo Inventory", type="secondary", use_container_width=True):
        st.session_state.simulated_stock = stock.copy()
        st.session_state.order_confirmed_msg = None
        st.session_state.last_deduction_summary = None
        st.session_state.confirmed_order_key = None
        st.success("Simulated stock restored to original balance.")
        st.rerun()

    st.divider()
    st.info("💡 **Live Stock Impact:** Confirmed orders atomically deduct ingredients from simulated stock, updating the replenishment dashboard in real time.")


# Page Hero Header
st.markdown(
    """
    <div class="rms-hero-card rms-hero-order" style="position:relative; overflow:hidden; background:radial-gradient(circle at 92% 10%, rgba(245, 158, 11, 0.09) 0%, transparent 45%), radial-gradient(circle at 8% 85%, rgba(239, 68, 68, 0.06) 0%, transparent 40%), #ffffff !important; border:1px solid #e2e8f0 !important; border-top:3.5px solid #f59e0b !important; color:#0f172a !important; padding:1.35rem 1.75rem !important; border-radius:16px !important; box-shadow:0 4px 20px -2px rgba(245, 158, 11, 0.08), 0 2px 6px -1px rgba(15, 23, 42, 0.03) !important; margin-bottom:1.5rem !important;">
        <div style="display:flex; align-items:center; gap:0.85rem;">
            <div class="rms-hero-icon-box" style="background:linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%) !important; border:1px solid #fed7aa !important; color:#ea580c !important; box-shadow:0 4px 10px rgba(245, 158, 11, 0.15) !important;">🛒</div>
            <div>
                <h1 class="rms-hero-title" style="color:#0f172a !important; font-size:1.45rem !important; font-weight:800 !important; margin:0 !important; font-family:'Plus Jakarta Sans', sans-serif !important; letter-spacing:-0.025em !important;">
                    Place Customer Order &amp; Inventory Depletion
                </h1>
                <div class="rms-hero-subtitle" style="color:#475569 !important; font-size:0.9rem !important; margin:0.4rem 0 0 0 !important; line-height:1.5 !important;">
                    Verify recipe requirements and atomically deduct operational kitchen stock in real time.
                </div>
            </div>
        </div>
        <div class="rms-badge-group" style="margin-top:0.75rem !important; display:flex !important; flex-wrap:wrap !important; gap:0.55rem !important;">
            <span class="rms-pill rms-pill-live" style="background:linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important; color:#047857 !important; border:1px solid #6ee7b7 !important; box-shadow:0 2px 6px rgba(16, 185, 129, 0.15) !important; font-weight:700 !important;"><span class="rms-pulse-dot"></span> Live Operational Stock</span>
            <span class="rms-pill rms-pill-model" style="background:linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%) !important; color:#c2410c !important; border:1px solid #fed7aa !important; box-shadow:0 2px 6px rgba(234, 88, 12, 0.15) !important; font-weight:700 !important;">🍲 BOM &amp; Wastage Engine</span>
            <span class="rms-pill rms-pill-info" style="background:linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%) !important; color:#7e22ce !important; border:1px solid #e9d5ff !important; box-shadow:0 2px 6px rgba(147, 51, 234, 0.15) !important; font-weight:700 !important;">⚡ Instant Stock Recalculation</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

if st.session_state.order_confirmed_msg:
    st.success(st.session_state.order_confirmed_msg)
    if st.session_state.last_deduction_summary:
        with st.expander("🔍 View Stock Deduction Details for Last Confirmed Order", expanded=True):
            st.dataframe(pd.DataFrame(st.session_state.last_deduction_summary), use_container_width=True)

# Order Selection Card
st.markdown(
    """
    <div class="rms-section-header">
        <span class="rms-section-number">📋</span>
        <h3 class="rms-section-title">Order Selection</h3>
    </div>
    <div class="rms-section-desc">Choose a menu item and specify number of servings to prepare.</div>
    """,
    unsafe_allow_html=True
)

with st.container(border=True):
    order_c1, order_c2 = st.columns([2.5, 1.5])
    with order_c1:
        menu_name = st.selectbox("Select Menu Item", menu_items["name"].tolist(), key="order_page_menu_item_select")
    with order_c2:
        order_qty = st.number_input("Order Quantity (Servings)", min_value=1, max_value=50, value=2, step=1, key="order_page_qty_input")

current_order_key = (menu_name, order_qty)
if st.session_state.last_order_key != current_order_key:
    st.session_state.order_confirmed_msg = None
    st.session_state.last_deduction_summary = None
    st.session_state.confirmed_order_key = None
    st.session_state.last_order_key = current_order_key

# Find active recipe and version
selected_menu = menu_items[menu_items["name"] == menu_name].iloc[0]
menu_item_id = selected_menu["id"]

selected_recipe = recipes[
    (recipes["menu_item_id"] == menu_item_id) & (recipes["is_active"] == 1)
]

if selected_recipe.empty:
    st.warning("⚠️ No active recipe found for this menu item.")
else:
    recipe_id = selected_recipe.iloc[0]["id"]
    recipe_name = selected_recipe.iloc[0]["name"]

    active_version = recipe_versions[
        (recipe_versions["recipe_id"] == recipe_id) & (recipe_versions["state"] == "ACTIVE")
    ]

    if active_version.empty:
        st.warning("⚠️ No active recipe version found for this menu item.")
    else:
        version_id = active_version.iloc[0]["id"]
        version_no = active_version.iloc[0]["version_no"]

        st.info(f"🍲 **Active Recipe:** **{recipe_name}** *(Version {version_no})*")

        required = recipe_ingredients[
            recipe_ingredients["recipe_version_id"] == version_id
        ].copy()

        if required.empty:
            st.warning("⚠️ No ingredients found for this recipe version.")
        else:
            required = required.merge(
                ingredients[["id", "name", "base_uom_id"]],
                left_on="ingredient_id",
                right_on="id",
                suffixes=("", "_ingredient")
            )

            uom_name_map = uom.set_index("id")["name"].to_dict()
            uom_code_map = uom.set_index("id")["code"].to_dict()

            calc_rows = []
            unsupported_conversions = []

            for _, r in required.iterrows():
                ing_id_val = r["ingredient_id"]
                ing_name_val = r["name"]
                recipe_qty_val = r["quantity"]
                wastage_pct_val = r["wastage_percent"]
                from_uom_id = r["uom_id"]
                base_uom_id = r["base_uom_id"]
                base_unit_name = uom_name_map.get(base_uom_id, f"Unit {base_uom_id}")
                base_unit_code = uom_code_map.get(base_uom_id, "")

                # Total required quantity with recipe wastage
                total_recipe_qty = recipe_qty_val * (1 + (wastage_pct_val / 100.0)) * order_qty
                converted_qty = convert_to_base_unit(total_recipe_qty, from_uom_id, base_uom_id, uom_conversions)

                if converted_qty is None:
                    unsupported_conversions.append(f"Unsupported conversion for '{ing_name_val}'.")
                    total_base_qty = None
                else:
                    total_base_qty = round(converted_qty, 4)

                calc_rows.append({
                    "ingredient_id": ing_id_val,
                    "Ingredient": ing_name_val,
                    "Recipe Qty / Serving": recipe_qty_val,
                    "Wastage %": wastage_pct_val,
                    "Order Servings": order_qty,
                    "Required Base Qty": total_base_qty,
                    "Base Unit": base_unit_code
                })

            for err in unsupported_conversions:
                st.error(err)

            st.markdown(
                """
                <div class="rms-section-header">
                    <span class="rms-section-number">1</span>
                    <h3 class="rms-section-title">Required Ingredients Calculation</h3>
                </div>
                <div class="rms-section-desc">Bill of Materials calculated for ordered servings including standard recipe wastage factors.</div>
                """,
                unsafe_allow_html=True
            )
            calc_df = pd.DataFrame(calc_rows)
            
            calc_display = calc_df[[
                "Ingredient", "Recipe Qty / Serving", "Wastage %",
                "Order Servings", "Required Base Qty", "Base Unit"
            ]].copy()

            styled_calc = calc_display.style.format({
                "Recipe Qty / Serving": "{:.4f}",
                "Wastage %": "{:.1f}%",
                "Required Base Qty": "{:.4f}"
            })

            st.dataframe(
                styled_calc,
                use_container_width=True,
                hide_index=True
            )

            # Live Stock Availability Check
            st.markdown(
                """
                <div class="rms-section-header">
                    <span class="rms-section-number">2</span>
                    <h3 class="rms-section-title">Live Stock Availability Check</h3>
                </div>
                <div class="rms-section-desc">Real-time comparison between required batch quantities and current simulated inventory balances.</div>
                """,
                unsafe_allow_html=True
            )
            current_sim_stock = st.session_state.simulated_stock
            sim_stock_map = current_sim_stock.groupby("ingredient_id")["qty_base"].sum().to_dict()
            recorded_ids = set(current_sim_stock["ingredient_id"].unique())

            availability_list = []
            shortage_list = []
            missing_records = []

            for item in calc_rows:
                i_id = item["ingredient_id"]
                r_qty = item["Required Base Qty"]

                if i_id not in recorded_ids:
                    missing_records.append(item["Ingredient"])

                avail = round(float(sim_stock_map.get(i_id, 0.0)), 4) if r_qty is not None else 0.0
                rem = round(avail - (r_qty or 0.0), 4)

                if r_qty is not None and avail < r_qty:
                    shortage_list.append({
                        "name": item["Ingredient"],
                        "short": round(r_qty - avail, 4),
                        "unit": item["Base Unit"]
                    })
                    status_str = "Insufficient"
                else:
                    status_str = "Available"

                availability_list.append({
                    "Ingredient": item["Ingredient"],
                    "Required Quantity": r_qty,
                    "Available Inventory": avail,
                    "Remaining After Order": rem,
                    "Unit": item["Base Unit"],
                    "Status": status_str
                })

            avail_df = pd.DataFrame(availability_list)

            styled_avail = (
                avail_df.style
                .format({
                    "Required Quantity": "{:.4f}",
                    "Available Inventory": "{:.4f}",
                    "Remaining After Order": "{:.4f}"
                })
                .map(style_availability_cell, subset=["Status"])
            )

            st.dataframe(
                styled_avail,
                use_container_width=True,
                hide_index=True
            )

            if missing_records:
                st.warning(f"⚠️ No stock record found for: {', '.join(missing_records)}. Stock is treated as 0.0.")

            # Order confirmation button
            is_already_confirmed = (st.session_state.get("confirmed_order_key") == current_order_key)
            can_confirm = (
                not unsupported_conversions
                and not shortage_list
                and order_qty > 0
                and not missing_records
            )

            st.markdown(
                """
                <div class="rms-section-header">
                    <span class="rms-section-number">3</span>
                    <h3 class="rms-section-title">Confirm Order & Deplete Stock</h3>
                </div>
                <div class="rms-section-desc">Commit transaction and deduct calculated ingredient quantities from simulated operational stock.</div>
                """,
                unsafe_allow_html=True
            )

            if is_already_confirmed:
                st.button("✅ Order Already Confirmed", disabled=True)
                if st.button("Place Another Order", type="primary"):
                    st.session_state.confirmed_order_key = None
                    st.session_state.order_confirmed_msg = None
                    st.session_state.last_deduction_summary = None
                    st.rerun()
            elif can_confirm:
                if st.button("🚀 Confirm Order & Deduct Inventory", type="primary"):
                    latest_stock = st.session_state.simulated_stock
                    deduction_log = []

                    for item in calc_rows:
                        i_id = item["ingredient_id"]
                        req_q = item["Required Base Qty"]
                        indices = latest_stock[latest_stock["ingredient_id"] == i_id].index
                        rem = req_q
                        for idx in indices:
                            val = latest_stock.at[idx, "qty_base"]
                            amt = min(val, rem)
                            latest_stock.at[idx, "qty_base"] -= amt
                            rem -= amt
                            if rem <= 0:
                                break

                        new_bal = round(latest_stock.groupby("ingredient_id")["qty_base"].sum().get(i_id, 0.0), 4)
                        deduction_log.append({
                            "Ingredient": item["Ingredient"],
                            "Deducted": req_q,
                            "Remaining Stock": new_bal,
                            "Unit": item["Base Unit"]
                        })

                    st.session_state.simulated_stock = latest_stock
                    st.session_state.confirmed_order_key = current_order_key
                    st.session_state.order_confirmed_msg = f"Order for {order_qty}x {menu_name} confirmed! Stock successfully deducted."
                    st.session_state.last_deduction_summary = deduction_log
                    st.rerun()
            else:
                st.button("Confirm Order & Deduct Inventory", disabled=True, help="Cannot confirm order due to ingredient shortages or missing data.")
                if shortage_list:
                    for s in shortage_list:
                        st.error(f"❌ Shortage: **{s['name']}** is short by **{s['short']} {s['unit']}**.")


# Return to dashboard link
st.markdown("---")
st.page_link("app.py", label="← Return to Replenishment Dashboard", icon="📊")
