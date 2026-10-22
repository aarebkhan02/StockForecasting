"""
Replenishment Engine for Restaurant Inventory & Forecast Dashboard.

Provides pure functions for:
- Master dataset loading and schema validation
- Holt-Winters additive trend and weekly seasonality forecasting (seasonal_periods=7)
- Dual-variance dynamic safety stock calculation:
    SS_i = z * sqrt(L_i * sigma_D_i^2 + D_hat_i^2 * sigma_L_i^2)
- Current safety buffer calculation:
    B_i = S_{i,0} - sum_{t=1}^{L_i} D_hat_{i,t}
- Daily inventory projection with verified incoming deliveries:
    S_t = S_{t-1} - D_hat_t + R_t
- Replenishment risk classification (Critical, At Risk, Sufficient, Unknown)
- Recommended replenishment order quantity calculation:
    Q_i = max(0, sum_{t=1}^{L_i+R} D_hat_{i,t} + SS_i - S_{i,0} - I_i)
- Procurement order status extraction
"""

import math
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import pandas as pd
import numpy as np
import streamlit as st
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def load_master_datasets(base_dir: Path) -> Dict[str, Any]:
    """
    Load restaurant master data, forecast historical data, lead-time metrics,
    and verified procurement files using project-relative paths.
    """
    data_dir = base_dir / "data-rms" / "data-rms"
    clean_dir = base_dir / "DataCleaned"
    forecast_dir = base_dir / "forecast_outputs"
    lead_dir = base_dir / "lead_time_outputs"

    warnings = []

    # 1. Historical Demand
    demand_file = forecast_dir / "demand_data.csv"
    if not demand_file.exists():
        demand_file = clean_dir / "daily_ingredient_demand.csv"
        warnings.append(f"Primary demand file not found. Falling back to {demand_file.name}.")

    if not demand_file.exists():
        raise FileNotFoundError("Historical demand data CSV could not be found.")

    demand_df = pd.read_csv(demand_file)
    demand_df["date"] = pd.to_datetime(demand_df["date"])
    demand_df = demand_df.sort_values(["ingredient_id", "date"]).reset_index(drop=True)

    # 2. Historical Lead Time Summary
    lead_file = lead_dir / "full_lead_time_summary.csv"
    if not lead_file.exists():
        raise FileNotFoundError(f"Lead-time summary CSV not found at {lead_file}")
    lead_df = pd.read_csv(lead_file)

    # 3. Model Evaluation metrics (MAE, RMSE)
    eval_file = forecast_dir / "holt_winters_evaluation.csv"
    eval_df = pd.read_csv(eval_file) if eval_file.exists() else pd.DataFrame()

    # 4. Master Ingredient and UOM Data
    ingredient_df = pd.read_csv(data_dir / "ingredient.csv")
    uom_df = pd.read_csv(data_dir / "unit_of_measure.csv")
    conversion_df = pd.read_csv(data_dir / "uom_conversion.csv")

    # 5. Verified Purchase Orders and Items
    po_file = data_dir / "purchase_order.csv"
    poi_file = data_dir / "purchase_order_item.csv"
    gr_file = data_dir / "goods_receipt.csv"
    gri_file = data_dir / "goods_receipt_item.csv"

    po_df = pd.read_csv(po_file) if po_file.exists() else pd.DataFrame()
    poi_df = pd.read_csv(poi_file) if poi_file.exists() else pd.DataFrame()
    gr_df = pd.read_csv(gr_file) if gr_file.exists() else pd.DataFrame()
    gri_df = pd.read_csv(gri_file) if gri_file.exists() else pd.DataFrame()

    # Match check between demand and lead-time data
    demand_ids = set(demand_df["ingredient_id"].unique())
    lead_ids = set(lead_df["ingredient_id"].unique())
    mismatch = demand_ids.symmetric_difference(lead_ids)
    if mismatch:
        warnings.append(f"Ingredient ID mismatch between demand and lead-time data: {mismatch}")

    return {
        "demand_df": demand_df,
        "lead_df": lead_df,
        "eval_df": eval_df,
        "ingredient_df": ingredient_df,
        "uom_df": uom_df,
        "conversion_df": conversion_df,
        "po_df": po_df,
        "poi_df": poi_df,
        "gr_df": gr_df,
        "gri_df": gri_df,
        "warnings": warnings,
    }


@st.cache_data(show_spinner=False)
def generate_holt_winters_forecasts(
    demand_df: pd.DataFrame,
    horizon: int = 7
) -> Dict[str, Any]:
    """
    Fit Holt-Winters additive trend and additive weekly seasonality (seasonal_periods=7)
    independently for each ingredient.
    
    Caches results and invalidates cache only when demand data or forecast horizon changes.
    Clips negative forecast values to 0.0.
    Derives forecast dates from the actual latest data date.
    """
    forecasts_by_ingredient = {}
    variance_by_ingredient = {}
    history_stats = {}
    warnings_by_ingredient = {}

    latest_date = demand_df["date"].max()
    forecast_dates = [latest_date + pd.Timedelta(days=i) for i in range(1, horizon + 1)]

    for ing_id in sorted(demand_df["ingredient_id"].unique()):
        sub = demand_df[demand_df["ingredient_id"] == ing_id].sort_values("date")
        ing_name = sub["ingredient_name"].iloc[0]
        base_uom_id = sub["base_uom_id"].iloc[0]

        # Ensure daily frequency
        series = sub.set_index("date")["daily_demand"].asfreq("D")
        
        # Check missing dates or NaNs
        nan_count = int(series.isna().sum())
        if nan_count > 0:
            warnings_by_ingredient[ing_id] = f"{nan_count} missing days interpolated."
            series = series.interpolate(method="linear")

        # Demand variance over historical observations
        sigma_d_sq = float(series.var()) if len(series) > 1 else 0.0
        mean_hist_demand = float(series.mean())

        # Fit Holt-Winters model: additive trend, additive seasonality (7-day week)
        try:
            model = ExponentialSmoothing(
                series,
                trend="add",
                seasonal="add",
                seasonal_periods=7,
                initialization_method="estimated"
            ).fit()
            raw_forecast = model.forecast(horizon)
            # Clip negative forecast values to zero
            clipped_forecast = raw_forecast.clip(lower=0.0)
            clipped_forecast.index = forecast_dates
        except Exception as e:
            warnings_by_ingredient[ing_id] = f"Holt-Winters fitting failed ({e}); used historical mean."
            clipped_forecast = pd.Series([max(0.0, mean_hist_demand)] * horizon, index=forecast_dates)

        forecasts_by_ingredient[ing_id] = clipped_forecast
        variance_by_ingredient[ing_id] = sigma_d_sq
        history_stats[ing_id] = {
            "name": ing_name,
            "base_uom_id": base_uom_id,
            "count": len(series),
            "min_date": series.index.min(),
            "max_date": series.index.max(),
            "hist_mean": mean_hist_demand,
            "hist_variance": sigma_d_sq,
        }

    return {
        "forecasts": forecasts_by_ingredient,
        "variance": variance_by_ingredient,
        "history_stats": history_stats,
        "warnings": warnings_by_ingredient,
        "latest_date": latest_date,
        "forecast_dates": forecast_dates,
    }


def get_verified_incoming_deliveries(
    po_df: pd.DataFrame,
    poi_df: pd.DataFrame,
    forecast_start_date: pd.Timestamp
) -> pd.DataFrame:
    """
    Extract verified, outstanding purchase orders and their arrival dates.
    Only includes POs in 'APPROVED' state with expected_date >= forecast_start_date.
    Avoids double counting already received items.
    """
    if po_df.empty or poi_df.empty:
        return pd.DataFrame(columns=[
            "po_number", "purchase_order_id", "ingredient_id",
            "quantity", "received_qty", "pending_qty", "expected_date", "uom_id"
        ])

    approved = po_df[po_df["state"] == "APPROVED"].copy()
    if approved.empty:
        return pd.DataFrame(columns=[
            "po_number", "purchase_order_id", "ingredient_id",
            "quantity", "received_qty", "pending_qty", "expected_date", "uom_id"
        ])

    approved["expected_date"] = pd.to_datetime(approved["expected_date"])
    # Include orders scheduled to arrive during or after the forecast start date
    valid_pos = approved[approved["expected_date"] >= forecast_start_date]

    merged = poi_df.merge(
        valid_pos[["id", "po_number", "expected_date", "state"]],
        left_on="purchase_order_id",
        right_on="id",
        suffixes=("_item", "_po")
    )

    merged["received_qty"] = merged["received_qty"].fillna(0.0)
    merged["pending_qty"] = merged["quantity"] - merged["received_qty"]
    # Only keep lines where there is positive pending stock
    merged = merged[merged["pending_qty"] > 0].copy()

    return merged[[
        "po_number", "purchase_order_id", "ingredient_id",
        "quantity", "received_qty", "pending_qty", "expected_date", "uom_id"
    ]]


def get_all_procurement_records(
    po_df: pd.DataFrame,
    poi_df: pd.DataFrame,
    ingredient_df: pd.DataFrame,
    uom_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Extract all open and active purchase order line items for procurement auditing.
    Identifies outstanding quantity, accepted received quantity, expected date, and partial/complete status.
    """
    if po_df.empty or poi_df.empty:
        return pd.DataFrame()

    # Active states: APPROVED, PARTIALLY_RECEIVED
    active_pos = po_df[po_df["state"].isin(["APPROVED", "PARTIALLY_RECEIVED"])].copy()
    if active_pos.empty:
        return pd.DataFrame()

    active_pos["expected_date"] = pd.to_datetime(active_pos["expected_date"])

    merged = poi_df.merge(
        active_pos[["id", "po_number", "state", "expected_date", "created_at"]],
        left_on="purchase_order_id",
        right_on="id",
        suffixes=("_item", "_po")
    )

    merged["received_qty"] = merged["received_qty"].fillna(0.0)
    merged["pending_qty"] = merged["quantity"] - merged["received_qty"]
    # Keep records with positive pending quantity
    merged = merged[merged["pending_qty"] > 0].copy()

    # Map ingredient name and UOM code
    ing_map = ingredient_df.set_index("id")["name"].to_dict()
    uom_map = uom_df.set_index("id")["code"].to_dict()

    merged["ingredient_name"] = merged["ingredient_id"].map(ing_map)
    merged["unit_code"] = merged["uom_id"].map(uom_map)
    merged["delivery_status"] = merged.apply(
        lambda r: "Partial Receipt (Remaining)" if r["received_qty"] > 0 else "Full Delivery Pending",
        axis=1
    )

    return merged[[
        "po_number", "ingredient_id", "ingredient_name", "unit_code",
        "quantity", "received_qty", "pending_qty", "expected_date",
        "state", "delivery_status"
    ]].sort_values("expected_date").reset_index(drop=True)


def calculate_dynamic_safety_stock(
    L_i: float,
    sigma_L_sq: float,
    sigma_D_sq: float,
    D_hat_mean: float,
    z: float = 1.645
) -> Tuple[float, Dict[str, float]]:
    """
    Calculate Dynamic Safety Stock using the dual-uncertainty formula:
    SS_i = z * sqrt(L_i * sigma_D_i^2 + D_hat_i^2 * sigma_L_i^2)

    Where:
    - z: Service level factor (default 1.645 for 95% nominal one-sided normal).
    - L_i: Mean full-delivery lead time in days.
    - sigma_D_sq: Historical daily demand variance.
    - D_hat_mean: Mean forecast daily demand over the replenishment coverage window.
    - sigma_L_sq: Historical full-delivery lead-time variance.

    Assumptions:
    - Demand and lead-time uncertainties are treated as independent.
    - Normal approximation is applied.
    """
    valid_L = max(0.0, float(L_i))
    valid_sigma_L_sq = max(0.0, float(sigma_L_sq))
    valid_sigma_D_sq = max(0.0, float(sigma_D_sq))
    valid_D_hat = max(0.0, float(D_hat_mean))
    valid_z = max(0.0, float(z))

    demand_var_component = valid_L * valid_sigma_D_sq
    lead_time_var_component = (valid_D_hat ** 2) * valid_sigma_L_sq
    combined_variance = demand_var_component + lead_time_var_component

    ss = valid_z * math.sqrt(combined_variance)

    breakdown = {
        "z": valid_z,
        "L_i": valid_L,
        "sigma_D_sq": valid_sigma_D_sq,
        "D_hat_mean": valid_D_hat,
        "sigma_L_sq": valid_sigma_L_sq,
        "demand_var_component": demand_var_component,
        "lead_time_var_component": lead_time_var_component,
        "combined_variance": combined_variance,
        "safety_stock": ss,
    }
    return ss, breakdown


def calculate_safety_buffer(
    current_stock: float,
    forecast_series: pd.Series,
    lead_time_days: float
) -> Tuple[float, float, bool]:
    """
    Calculate the Current Safety Buffer ("Itna hai currently"):
    B_i = S_{i,0} - sum_{t=1}^{L_i} D_hat_{i,t}

    Where:
    - S_{i,0} is current verified stock
    - D_hat_{i,t} is forecast daily demand
    - Fractional lead times are handled by prorating:
        Demand_LT = sum_{t=1}^{floor(L)} D_hat_t + fraction * D_hat_{ceil(L)}

    Returns:
    (current_safety_buffer, lead_time_demand, horizon_exceeded)
    """
    horizon = len(forecast_series)
    d_full = int(math.floor(lead_time_days))
    d_frac = lead_time_days - d_full
    horizon_exceeded = lead_time_days > horizon

    if d_full < horizon:
        full_days_demand = float(forecast_series.iloc[:d_full].sum())
        frac_demand = float(d_frac * forecast_series.iloc[d_full]) if d_full < len(forecast_series) else 0.0
        lt_demand = full_days_demand + frac_demand
    else:
        # If lead time exceeds horizon, sum available forecast
        lt_demand = float(forecast_series.sum())

    buffer = current_stock - lt_demand
    return buffer, lt_demand, horizon_exceeded


def project_stock_trajectory(
    current_stock: float,
    forecast_series: pd.Series,
    incoming_df: pd.DataFrame,
    ingredient_id: int,
    lead_time_days: float,
) -> Dict[str, Any]:
    """
    Perform daily stock projection:
    projected_stock[t] = projected_stock[t-1] - forecast_demand[t] + confirmed_receipts[t]

    Starts from current_stock (at t=0, latest data date).
    Incoming stock is credited ONLY on its expected arrival day.
    Identifies stockout date and projected stock at expected full delivery time ceil(L_i).
    Separates physically available stock (max(0, projected)) from cumulative shortage.
    """
    days = len(forecast_series)
    dates = forecast_series.index.tolist()

    ing_incoming = incoming_df[incoming_df["ingredient_id"] == ingredient_id] if not incoming_df.empty else pd.DataFrame()

    trajectory = []
    running_unconstrained = current_stock
    stockout_day = None
    stockout_date = None
    stock_at_delivery = None

    delivery_day_int = max(1, int(math.ceil(lead_time_days)))

    for step_idx, f_date in enumerate(dates, start=1):
        f_demand = float(forecast_series.iloc[step_idx - 1])

        # Incoming arrivals strictly on day t
        if not ing_incoming.empty:
            arrivals = ing_incoming[ing_incoming["expected_date"].dt.normalize() == pd.to_datetime(f_date).normalize()]
            incoming_qty = float(arrivals["pending_qty"].sum())
        else:
            incoming_qty = 0.0

        running_unconstrained = running_unconstrained - f_demand + incoming_qty
        phys_available = max(0.0, running_unconstrained)
        shortage = max(0.0, -running_unconstrained)

        if step_idx == delivery_day_int and stock_at_delivery is None:
            stock_at_delivery = running_unconstrained

        if running_unconstrained <= 0.0 and stockout_day is None:
            stockout_day = step_idx
            stockout_date = f_date.strftime("%Y-%m-%d")

        trajectory.append({
            "day": step_idx,
            "date": f_date,
            "date_str": f_date.strftime("%Y-%m-%d"),
            "forecast_demand": f_demand,
            "confirmed_receipts": incoming_qty,
            "projected_unconstrained": running_unconstrained,
            "physically_available": phys_available,
            "cumulative_shortage": shortage,
        })

    if stock_at_delivery is None:
        stock_at_delivery = running_unconstrained

    traj_df = pd.DataFrame(trajectory)

    return {
        "trajectory_df": traj_df,
        "stockout_day": stockout_day,
        "stockout_date": stockout_date,
        "stock_at_delivery": stock_at_delivery,
        "delivery_day_int": delivery_day_int,
    }


def classify_risk(
    days_to_stockout: Optional[int],
    stockout_date: Optional[str],
    lead_time_days: float,
    risk_horizon: int,
    stock_at_delivery: float,
    safety_stock: float,
    current_safety_buffer: float,
    has_sufficient_data: bool = True
) -> Tuple[str, str]:
    """
    Classify replenishment risk:
    - Stockout / Critical: Days until stockout <= expected full-delivery lead time.
    - At Risk: Stockout after lead time but <= H, OR stock at expected delivery < safety stock, OR current safety buffer < safety stock.
    - Sufficient: Neither critical nor at risk conditions apply.
    - Unknown / Insufficient Data: Essential data missing or unreliable.
    """
    if not has_sufficient_data:
        return "Unknown", "Insufficient reliable data to assess replenishment risk."

    # 1. Critical
    if days_to_stockout is not None and days_to_stockout <= lead_time_days:
        return (
            "Critical",
            f"Projected stockout on Day {days_to_stockout} ({stockout_date}), earlier than or equal to lead time ({lead_time_days:.1f}d). Stockout occurs before replenishment could arrive."
        )

    # 2. At Risk
    if days_to_stockout is not None and days_to_stockout <= risk_horizon:
        return (
            "At Risk",
            f"Projected stockout on Day {days_to_stockout} ({stockout_date}), after lead time but within risk horizon ({risk_horizon}d)."
        )

    if stock_at_delivery < safety_stock:
        shortfall = safety_stock - stock_at_delivery
        return (
            "At Risk",
            f"Projected stock at expected delivery day ({stock_at_delivery:.1f}) falls below required safety stock ({safety_stock:.1f}) by {shortfall:.1f}."
        )

    if current_safety_buffer < safety_stock:
        buf_shortfall = safety_stock - current_safety_buffer
        return (
            "At Risk",
            f"Current safety buffer ({current_safety_buffer:.1f}) is below required safety stock ({safety_stock:.1f}) by {buf_shortfall:.1f}."
        )

    # 3. Sufficient
    return (
        "Sufficient",
        f"Projected stock and safety buffer remain adequate throughout the horizon ({risk_horizon}d) with no stockout predicted."
    )


def calculate_replenishment_recommendation(
    current_stock: float,
    forecast_series: pd.Series,
    lead_time_days: float,
    review_period: float,
    safety_stock: float,
    incoming_df: pd.DataFrame,
    ingredient_id: int,
    latest_date: pd.Timestamp
) -> Dict[str, Any]:
    """
    Calculate replenishment order quantity:
    Q_i = max(0, sum_{t=1}^{L_i+R} D_hat_{i,t} + SS_i - S_{i,0} - Incoming_i)

    Handles fractional lead time by prorating the final fractional day demand.
    Restricts Incoming_i strictly to verified receipts arriving within the coverage period.
    """
    coverage_days = lead_time_days + review_period
    horizon = len(forecast_series)

    is_coverage_complete = coverage_days <= horizon
    coverage_ceil = min(horizon, int(math.ceil(coverage_days)))
    d_full = int(math.floor(coverage_days))
    d_frac = coverage_days - d_full

    if d_full < horizon:
        full_days_demand = float(forecast_series.iloc[:d_full].sum())
        frac_day_demand = float(d_frac * forecast_series.iloc[d_full]) if d_full < len(forecast_series) else 0.0
        demand_cov = full_days_demand + frac_day_demand
    else:
        demand_cov = float(forecast_series.iloc[:horizon].sum())

    # Verified incoming deliveries arriving within the coverage period
    cov_end_date = latest_date + pd.Timedelta(days=coverage_ceil)
    if not incoming_df.empty:
        ing_incoming = incoming_df[incoming_df["ingredient_id"] == ingredient_id]
        eligible_incoming = float(ing_incoming[ing_incoming["expected_date"] <= cov_end_date]["pending_qty"].sum())
    else:
        eligible_incoming = 0.0

    # Policy Formula
    q_raw = max(0.0, demand_cov + safety_stock - (current_stock + eligible_incoming))
    q_recommended = round(q_raw, 2)

    warning = None
    if not is_coverage_complete:
        warning = f"Replenishment coverage ({coverage_days:.1f} days) exceeds available forecast horizon ({horizon} days). Quantity represents partial horizon coverage."

    return {
        "coverage_days": coverage_days,
        "demand_cov": demand_cov,
        "eligible_incoming": eligible_incoming,
        "q_raw": q_raw,
        "q_recommended": q_recommended,
        "is_coverage_complete": is_coverage_complete,
        "warning": warning,
    }


def compute_all_replenishment_metrics(
    simulated_stock_df: pd.DataFrame,
    master_data: Dict[str, Any],
    forecast_results: Dict[str, Any],
    z_score: float = 1.645,
    review_period: float = 1.0,
    risk_horizon: int = 7
) -> Dict[str, Any]:
    """
    Generate unified replenishment metrics and recommendation table across all ingredients.
    Uses simulated_stock_df as the single live source of truth for stock.
    Calculates both Required Safety Stock (SS_i) and Current Safety Buffer (B_i).
    """
    lead_df = master_data["lead_df"]
    ingredient_df = master_data["ingredient_df"]
    uom_df = master_data["uom_df"]
    eval_df = master_data["eval_df"]
    po_df = master_data["po_df"]
    poi_df = master_data["poi_df"]

    forecasts = forecast_results["forecasts"]
    variances = forecast_results["variance"]
    latest_date = forecast_results["latest_date"]
    forecast_dates = forecast_results["forecast_dates"]

    # Current stock from live simulated stock state
    current_stock_map = simulated_stock_df.groupby("ingredient_id")["qty_base"].sum().to_dict()
    recorded_stock_ids = set(simulated_stock_df["ingredient_id"].unique())

    # Verified incoming deliveries
    forecast_start_date = latest_date + pd.Timedelta(days=1)
    incoming_df = get_verified_incoming_deliveries(po_df, poi_df, forecast_start_date)
    all_procurement_df = get_all_procurement_records(po_df, poi_df, ingredient_df, uom_df)

    # Unit maps
    uom_map = uom_df.set_index("id")["name"].to_dict()
    uom_code_map = uom_df.set_index("id")["code"].to_dict()

    rows = []
    trajectories = {}
    safety_stock_breakdowns = {}

    for _, ing_row in ingredient_df.iterrows():
        ing_id = int(ing_row["id"])
        ing_name = ing_row["name"]
        base_uom_id = int(ing_row["base_uom_id"])
        base_uom_name = uom_map.get(base_uom_id, f"Unit {base_uom_id}")
        base_uom_code = uom_code_map.get(base_uom_id, "")
        static_reorder_level = ing_row.get("reorder_level", np.nan)
        static_reorder_qty = ing_row.get("reorder_qty", np.nan)

        data_warnings = []

        # Current stock check
        if ing_id not in recorded_stock_ids:
            data_warnings.append("Missing record in current simulated stock balance; treated as 0.0.")
            current_stock = 0.0
        else:
            current_stock = float(current_stock_map.get(ing_id, 0.0))

        # Forecast lookup
        if ing_id not in forecasts:
            data_warnings.append("No forecast model available.")
            forecast_series = pd.Series([0.0] * risk_horizon, index=forecast_dates)
            sigma_d_sq = 0.0
            avg_forecast_daily = 0.0
        else:
            forecast_series = forecasts[ing_id]
            sigma_d_sq = variances.get(ing_id, 0.0)
            avg_forecast_daily = float(forecast_series.mean())

        # Lead time lookup
        lead_match = lead_df[lead_df["ingredient_id"] == ing_id]
        if lead_match.empty:
            data_warnings.append("No historical lead-time record found in full_lead_time_summary.csv.")
            lead_time_days = 3.0
            median_lead_time = 3.0
            sigma_l_sq = 1.0
            full_deliveries = 0
            max_lead_time = 3.0
            lead_time_uncertainty = "High (Missing)"
        else:
            l_row = lead_match.iloc[0]
            lead_time_days = float(l_row["avg_full_lead_time_days"])
            median_lead_time = float(l_row.get("median_full_lead_time_days", lead_time_days))
            sigma_l_sq = float(l_row["full_lead_time_variance"])
            full_deliveries = int(l_row["full_deliveries"])
            max_lead_time = float(l_row.get("max_full_lead_time_days", lead_time_days))
            lead_time_uncertainty = "High Confidence" if full_deliveries >= 50 else ("Moderate" if full_deliveries >= 25 else "Low Confidence (Few samples)")

        # 1. Required Safety Stock ("Itna hona chahiye")
        ss_val, ss_breakdown = calculate_dynamic_safety_stock(
            lead_time_days, sigma_l_sq, sigma_d_sq, avg_forecast_daily, z=z_score
        )
        safety_stock_breakdowns[ing_id] = ss_breakdown

        # 2. Current Safety Buffer ("Itna hai currently")
        curr_buffer, lt_demand, lt_exceeded = calculate_safety_buffer(
            current_stock, forecast_series, lead_time_days
        )
        if lt_exceeded:
            data_warnings.append(f"Lead time ({lead_time_days:.1f}d) exceeds 7-day forecast horizon.")

        buffer_status = "Adequate" if curr_buffer >= ss_val else "Deficit"
        buffer_deficit = max(0.0, ss_val - curr_buffer)

        # 3. Trajectory & Stockout
        proj = project_stock_trajectory(
            current_stock, forecast_series, incoming_df, ing_id, lead_time_days
        )
        trajectories[ing_id] = proj

        # 4. Risk Classification
        has_sufficient_data = len(data_warnings) == 0
        risk_level, risk_reason = classify_risk(
            proj["stockout_day"],
            proj["stockout_date"],
            lead_time_days,
            risk_horizon,
            proj["stock_at_delivery"],
            ss_val,
            curr_buffer,
            has_sufficient_data=has_sufficient_data
        )

        # 5. Order Recommendation
        recom = calculate_replenishment_recommendation(
            current_stock,
            forecast_series,
            lead_time_days,
            review_period,
            ss_val,
            incoming_df,
            ing_id,
            latest_date
        )
        if recom["warning"]:
            data_warnings.append(recom["warning"])

        # Historical evaluation metrics lookup
        eval_match = eval_df[eval_df["ingredient"] == ing_name] if not eval_df.empty else pd.DataFrame()
        hist_mae = float(eval_match.iloc[0]["MAE"]) if not eval_match.empty else np.nan
        hist_rmse = float(eval_match.iloc[0]["RMSE"]) if not eval_match.empty else np.nan

        rows.append({
            "ingredient_id": ing_id,
            "ingredient_name": ing_name,
            "base_uom": base_uom_name,
            "base_uom_code": base_uom_code,
            "current_stock": current_stock,
            "avg_forecast_daily": avg_forecast_daily,
            "lead_time_days": lead_time_days,
            "median_lead_time_days": median_lead_time,
            "lead_time_variance": sigma_l_sq,
            "full_deliveries": full_deliveries,
            "max_lead_time_days": max_lead_time,
            "lead_time_uncertainty": lead_time_uncertainty,
            "safety_stock": ss_val,
            "current_safety_buffer": curr_buffer,
            "lead_time_demand": lt_demand,
            "safety_buffer_status": buffer_status,
            "safety_buffer_deficit": buffer_deficit,
            "stock_at_delivery": proj["stock_at_delivery"],
            "days_to_stockout": proj["stockout_day"],
            "stockout_date": proj["stockout_date"],
            "eligible_incoming": recom["eligible_incoming"],
            "coverage_days": recom["coverage_days"],
            "coverage_demand": recom["demand_cov"],
            "q_raw": recom["q_raw"],
            "recommended_order_qty": recom["q_recommended"],
            "is_coverage_complete": recom["is_coverage_complete"],
            "risk_status": risk_level,
            "risk_reason": risk_reason,
            "hist_mae": hist_mae,
            "hist_rmse": hist_rmse,
            "data_warnings": "; ".join(data_warnings) if data_warnings else "None",
        })

    summary_df = pd.DataFrame(rows)

    # Aggregated counts
    total_ingredients_tracked = len(summary_df)
    critical_count = int((summary_df["risk_status"] == "Critical").sum())
    at_risk_count = int((summary_df["risk_status"] == "At Risk").sum())
    sufficient_count = int((summary_df["risk_status"] == "Sufficient").sum())
    unknown_count = int((summary_df["risk_status"] == "Unknown").sum())
    replenishment_required_count = int((summary_df["recommended_order_qty"] > 0).sum())

    # Recommended quantity totals by base unit
    totals_by_unit = (
        summary_df.groupby("base_uom")["recommended_order_qty"]
        .sum()
        .to_dict()
    )

    return {
        "summary_df": summary_df,
        "trajectories": trajectories,
        "safety_stock_breakdowns": safety_stock_breakdowns,
        "incoming_df": incoming_df,
        "all_procurement_df": all_procurement_df,
        "total_ingredients_tracked": total_ingredients_tracked,
        "critical_count": critical_count,
        "at_risk_count": at_risk_count,
        "sufficient_count": sufficient_count,
        "unknown_count": unknown_count,
        "replenishment_required_count": replenishment_required_count,
        "totals_by_unit": totals_by_unit,
        "forecast_dates": forecast_dates,
        "latest_date": latest_date,
    }
