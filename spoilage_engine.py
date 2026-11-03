"""
Spoilage and Expiry-Aware Replenishment Engine for Restaurant RMS.

Implements pure calculation functions for:
- Batch-level physical inventory reconstruction from goods receipt items and current stock.
- FEFO (First Expire, First Out) demand allocation and batch depletion simulation.
- Usable stock vs physical stock tracking.
- Daily expiry waste quantification and financial costing using verified batch unit costs.
- Projected unmet demand calculation based strictly on unexpired usable inventory.
- Expiry-adjusted replenishment order recommendations.
- Audit of estimated preparation waste (recipe wastage_percent) vs recorded batch expiry waste.
"""

import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


def get_ingredient_prep_waste_percentages(
    master_data: Dict[str, Any],
    base_dir: Optional[Path] = None
) -> Dict[int, Dict[str, Any]]:
    """
    Extract verified recipe preparation waste percentage per ingredient.
    
    Data analysis findings:
    1. 'wastage_percent' in recipe_ingredient.csv represents nominal kitchen preparation
       trim allowance on recipe requirement (Q_total = Q_net * (1 + p/100)).
    2. Historical demand in daily_ingredient_demand.csv was computed from sales_demand_detail.csv
       strictly using net recipe quantities without adding wastage_percent.
    3. Holt-Winters forecasts therefore represent net recipe consumption.
    4. For forecast demand, estimated preparation waste is calculated once as:
       Estimated Preparation Waste = Daily Forecast Demand * (p_waste / 100).
    5. This percentage is mapped using the historical sales-weighted recipe wastage percentage
       from sales_demand_detail.csv (falling back to recipe_ingredient.csv mean).
    """
    if base_dir is None:
        base_dir = Path(__file__).parent

    clean_dir = base_dir / "DataCleaned"
    sales_file = clean_dir / "sales_demand_detail.csv"
    data_dir = base_dir / "data-rms" / "data-rms"
    ri_file = data_dir / "recipe_ingredient.csv"

    waste_map = {}

    # Recipe-level stats fallback
    ri_means = {}
    if ri_file.exists():
        ri_df = pd.read_csv(ri_file)
        ri_means = ri_df.groupby("ingredient_id")["wastage_percent"].agg(["mean", "min", "max", "count"]).to_dict("index")

    # Historical sales-weighted recipe wastage percentage
    sales_weighted = {}
    if sales_file.exists():
        sales_df = pd.read_csv(sales_file)
        for ing_id, grp in sales_df.groupby("ingredient_id"):
            tot_qty = (grp["quantity"] * grp["ingredient_recipe_qty"]).sum()
            if tot_qty > 0:
                weighted_pct = (grp["quantity"] * grp["ingredient_recipe_qty"] * grp["wastage_percent"]).sum() / tot_qty
                sales_weighted[ing_id] = round(float(weighted_pct), 4)

    # Compile for all ingredients
    ingredient_df = master_data.get("ingredient_df", pd.DataFrame())
    if not ingredient_df.empty:
        for _, ing_row in ingredient_df.iterrows():
            i_id = int(ing_row["id"])
            if i_id in sales_weighted:
                pct = sales_weighted[i_id]
                source = "Historical Sales-Weighted Recipe Trim %"
            elif i_id in ri_means:
                pct = round(float(ri_means[i_id]["mean"]), 4)
                source = "Recipe Ingredient Mean Trim %"
            else:
                pct = 0.0
                source = "Not Available"

            stats = ri_means.get(i_id, {"min": pct, "max": pct, "count": 0})
            waste_map[i_id] = {
                "prep_waste_pct": pct,
                "source": source,
                "min_pct": round(float(stats.get("min", pct)), 2),
                "max_pct": round(float(stats.get("max", pct)), 2),
                "recipe_count": int(stats.get("count", 0)),
            }

    return waste_map


def get_active_ingredient_batches(
    simulated_stock_df: pd.DataFrame,
    gri_df: pd.DataFrame,
    gr_df: pd.DataFrame,
    snapshot_date: pd.Timestamp = pd.Timestamp("2026-09-22")
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Reconstruct active physical batches for each ingredient from verified goods receipts.
    Allocates current stock to the most recent physical receipts in reverse
    chronological order, sorted FEFO (by expiry date ascending).

    Uses actual batch quantities, receipt dates, expiry dates, and unit costs.
    Does not fabricate batch records or assume expiry dates.

    Limitation note:
    Batch allocation reconstructs physical batches by mapping current unexpired stock balance
    to the most recent Goods Receipt Note items (FIFO receipt order). This provides an
    estimated batch-level reconstruction since individual kitchen sale consumption entries
    in the stock ledger were logged against ingredient totals rather than specific batch IDs.
    """
    if gri_df.empty or gr_df.empty:
        return {}

    # Merge receipt items with receipt header for date
    gri_gr = gri_df.merge(
        gr_df[["id", "received_at", "state"]],
        left_on="goods_receipt_id",
        right_on="id",
        suffixes=("_item", "_gr")
    ).copy()
    gri_gr["received_at"] = pd.to_datetime(gri_gr["received_at"])
    gri_gr["expiry_date"] = pd.to_datetime(gri_gr["expiry_date"])

    stock_map = simulated_stock_df.groupby("ingredient_id")["qty_base"].sum().to_dict()
    active_batches = {}

    for ing_id, curr_stock in stock_map.items():
        curr_stock = float(curr_stock)
        if curr_stock <= 1e-5:
            active_batches[ing_id] = []
            continue

        # Recent receipts for this ingredient in reverse chronological order
        ing_recs = gri_gr[gri_gr["ingredient_id"] == ing_id].sort_values(
            ["received_at", "id_item"], ascending=[False, False]
        )

        rem = curr_stock
        assigned = []
        for _, r in ing_recs.iterrows():
            b_qty = min(rem, float(r["accepted_qty"]))
            if b_qty > 1e-5:
                assigned.append({
                    "batch_number": str(r["batch_number"]),
                    "goods_receipt_id": int(r["goods_receipt_id"]),
                    "received_at": r["received_at"],
                    "expiry_date": r["expiry_date"],
                    "batch_stock": round(b_qty, 4),
                    "accepted_qty": float(r["accepted_qty"]),
                    "unit_cost": float(r["unit_cost"]),
                })
                rem -= b_qty
            if rem <= 1e-5:
                break

        # Sort assigned batches FEFO: earliest expiry first, then earliest receipt
        assigned.sort(key=lambda x: (x["expiry_date"], x["received_at"]))
        active_batches[ing_id] = assigned

    return active_batches


def simulate_fefo_trajectory(
    batches: List[Dict[str, Any]],
    forecast_series: pd.Series,
    incoming_df: pd.DataFrame,
    ingredient_id: int,
    lead_time_days: float,
    prep_waste_pct: float = 0.0,
    unit_cost_fallback: float = 0.0
) -> Dict[str, Any]:
    """
    Simulate daily FEFO consumption, expiry waste, and unmet demand over the forecast horizon.

    Rules:
    - Batches are consumed strictly in expiry-date order (FEFO).
    - Documented expiry-day rule: A batch becomes unusable on the date expiry_date <= day_date.
      Any unconsumed stock in that batch is removed as expiry waste on that date.
    - Usable stock on day t is unexpired batch stock plus verified incoming deliveries.
    - Day t requirement includes applicable estimated preparation waste without double counting:
      Requirement_t = Forecast_Demand_t * (1 + prep_waste_pct / 100).
    - Demand is satisfied first from unexpired dated batches (FEFO), then from incoming arrivals.
    - If required quantity exceeds usable stock on day t, the difference is Unmet Demand.
    - The same quantity is never double-counted as both consumed stock and expiry waste.
    """
    dates = forecast_series.index.tolist()
    days_count = len(dates)

    # Deep copy active batches for this simulation
    curr_batches = [
        {
            "batch_number": b["batch_number"],
            "goods_receipt_id": b.get("goods_receipt_id"),
            "received_at": b["received_at"],
            "expiry_date": b["expiry_date"],
            "batch_stock": float(b["batch_stock"]),
            "unit_cost": float(b["unit_cost"]),
        }
        for b in batches
    ]

    ing_incoming = (
        incoming_df[incoming_df["ingredient_id"] == ingredient_id].copy()
        if not incoming_df.empty
        else pd.DataFrame()
    )

    trajectory = []
    total_expiry_waste_qty = 0.0
    total_expiry_waste_cost = 0.0
    total_unmet_demand = 0.0
    total_forecast_demand = float(forecast_series.sum())
    total_prep_waste = 0.0

    initial_physical_stock = sum(b["batch_stock"] for b in curr_batches)
    stockout_day = None
    stockout_date = None
    first_spoilage_day = None
    first_spoilage_date = None
    usable_stock_at_delivery = None

    delivery_day_int = max(1, int(math.ceil(lead_time_days)))

    # Next-Day Demand: demand for Day 1
    next_day_demand = float(forecast_series.iloc[0]) if len(forecast_series) > 0 else 0.0

    for step_idx, f_date in enumerate(dates, start=1):
        f_norm = pd.to_datetime(f_date).normalize()
        f_demand = float(forecast_series.iloc[step_idx - 1])

        # Estimated preparation waste for day t
        prep_waste_t = round(f_demand * (prep_waste_pct / 100.0), 4)
        total_prep_waste += prep_waste_t
        total_required_today = f_demand + prep_waste_t

        # 1. Process batch expiries at the start of day t
        # Project documented expiry rule: batch becomes unusable on expiry_date <= f_norm
        expired_today_qty = 0.0
        expired_today_cost = 0.0
        expired_batches_today = []

        for b in curr_batches:
            if b["expiry_date"] <= f_norm and b["batch_stock"] > 1e-5:
                qty_exp = b["batch_stock"]
                cost_exp = qty_exp * b["unit_cost"]
                expired_today_qty += qty_exp
                expired_today_cost += cost_exp
                expired_batches_today.append({
                    "batch_number": b["batch_number"],
                    "expired_qty": qty_exp,
                    "unit_cost": b["unit_cost"],
                    "cost": cost_exp
                })
                b["batch_stock"] = 0.0

        if expired_today_qty > 0 and first_spoilage_day is None:
            first_spoilage_day = step_idx
            first_spoilage_date = f_norm.strftime("%Y-%m-%d")

        total_expiry_waste_qty += expired_today_qty
        total_expiry_waste_cost += expired_today_cost

        # Determine Days Until Expiry for day t:
        # Rule: Show nearest upcoming expiry among relevant usable batches.
        # When a batch is expired (expiry_date <= f_norm), display '0 (Expired)'.
        # If no batch records exist, display 'N/A'.
        if not batches:
            days_until_exp_val = np.nan
            days_until_exp_str = "N/A"
        else:
            usable_with_stock = [
                b for b in curr_batches
                if b["expiry_date"] > f_norm and b["batch_stock"] > 1e-5
            ]
            if usable_with_stock:
                nearest_b = min(usable_with_stock, key=lambda x: x["expiry_date"])
                days_until_exp_val = (nearest_b["expiry_date"] - f_norm).days
                days_until_exp_str = (
                    f"{days_until_exp_val} day"
                    if days_until_exp_val == 1
                    else f"{days_until_exp_val} days"
                )
            else:
                unexpired_batches = [
                    b for b in curr_batches
                    if b["expiry_date"] > f_norm
                ]
                if unexpired_batches:
                    nearest_b = min(unexpired_batches, key=lambda x: x["expiry_date"])
                    days_until_exp_val = (nearest_b["expiry_date"] - f_norm).days
                    days_until_exp_str = (
                        f"{days_until_exp_val} day"
                        if days_until_exp_val == 1
                        else f"{days_until_exp_val} days"
                    )
                else:
                    days_until_exp_val = 0
                    days_until_exp_str = "0 (Expired)"

        # 2. Check verified incoming deliveries arriving on day t
        incoming_qty = 0.0
        if not ing_incoming.empty:
            arrivals = ing_incoming[
                ing_incoming["expected_date"].dt.normalize() == f_norm
            ]
            incoming_qty = float(arrivals["pending_qty"].sum())

        # Usable stock on hand before demand
        usable_before_demand = sum(
            b["batch_stock"] for b in curr_batches if b["expiry_date"] > f_norm
        )
        total_available = usable_before_demand + incoming_qty

        # 3. Allocate forecast requirement in FEFO order
        rem_demand = total_required_today
        consumed_dated = 0.0

        # Sort remaining usable batches by expiry date ascending
        curr_batches.sort(key=lambda x: (x["expiry_date"], x["received_at"]))
        for b in curr_batches:
            if b["expiry_date"] > f_norm and b["batch_stock"] > 1e-5:
                alloc = min(b["batch_stock"], rem_demand)
                b["batch_stock"] -= alloc
                rem_demand -= alloc
                consumed_dated += alloc
                if rem_demand <= 1e-5:
                    break

        # Consume from incoming delivery if dated batches exhausted
        consumed_incoming = 0.0
        rem_incoming = incoming_qty
        if rem_demand > 1e-5 and rem_incoming > 0:
            alloc_inc = min(rem_incoming, rem_demand)
            rem_incoming -= alloc_inc
            rem_demand -= alloc_inc
            consumed_incoming += alloc_inc

        unmet_today = max(0.0, rem_demand)
        total_unmet_demand += unmet_today
        total_consumed_today = consumed_dated + consumed_incoming

        # Usable ending stock (unexpired dated batches + remaining incoming)
        rem_dated_usable = sum(
            b["batch_stock"] for b in curr_batches if b["expiry_date"] > f_norm
        )
        ending_usable_stock = rem_dated_usable + rem_incoming

        # Stockout detection under expiry awareness
        if (ending_usable_stock <= 1e-5 or unmet_today > 1e-5) and stockout_day is None:
            stockout_day = step_idx
            stockout_date = f_norm.strftime("%Y-%m-%d")

        if step_idx == delivery_day_int and usable_stock_at_delivery is None:
            usable_stock_at_delivery = ending_usable_stock

        trajectory.append({
            "day": step_idx,
            "date": f_norm,
            "date_str": f_norm.strftime("%Y-%m-%d"),
            "days_until_expiry": days_until_exp_val,
            "days_until_expiry_str": days_until_exp_str,
            "next_day_demand": round(next_day_demand, 2),
            "daily_forecast_demand": round(f_demand, 2),
            "estimated_prep_waste": round(prep_waste_t, 2),
            "total_requirement": round(total_required_today, 2),
            "usable_before_demand": round(usable_before_demand, 2),
            "incoming_qty": round(incoming_qty, 2),
            "consumed_stock": round(total_consumed_today, 2),
            "expiring_qty": round(expired_today_qty, 2),
            "expiring_cost": round(expired_today_cost, 2),
            "projected_usable_stock": round(ending_usable_stock, 2),
            "unmet_demand": round(unmet_today, 2),
            "active_batch_count": sum(1 for b in curr_batches if b["batch_stock"] > 1e-5 and b["expiry_date"] > f_norm),
        })

    if usable_stock_at_delivery is None:
        usable_stock_at_delivery = trajectory[-1]["projected_usable_stock"] if trajectory else 0.0

    traj_df = pd.DataFrame(trajectory)

    return {
        "trajectory_df": traj_df,
        "initial_physical_stock": initial_physical_stock,
        "next_day_demand": round(next_day_demand, 2),
        "total_expiry_waste_qty": round(total_expiry_waste_qty, 4),
        "total_expiry_waste_cost": round(total_expiry_waste_cost, 2),
        "total_unmet_demand": round(total_unmet_demand, 4),
        "total_forecast_demand": round(total_forecast_demand, 4),
        "total_prep_waste": round(total_prep_waste, 4),
        "stockout_day": stockout_day,
        "stockout_date": stockout_date,
        "first_spoilage_day": first_spoilage_day,
        "first_spoilage_date": first_spoilage_date,
        "usable_stock_at_delivery": usable_stock_at_delivery,
        "ending_batches": [b for b in curr_batches if b["batch_stock"] > 1e-5],
    }


def compute_all_spoilage_metrics(
    simulated_stock_df: pd.DataFrame,
    master_data: Dict[str, Any],
    forecast_results: Dict[str, Any],
    replenishment_metrics: Dict[str, Any],
    review_period: float = 1.0,
    risk_horizon: int = 7,
    base_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Unified calculation engine for Spoilage Forecasting page.
    Generates:
    1. Daily Demand & Spoilage Forecast table (1 row per ingredient per forecast date, 9 columns).
    2. Expiry-Aware Reorder Recommendations table (5 essential columns + side-by-side baseline).
    3. Technical batch audit tables and metrics for optional expanders.
    """
    if base_dir is None:
        base_dir = Path(__file__).parent

    gri_df = master_data["gri_df"]
    gr_df = master_data["gr_df"]
    ingredient_df = master_data["ingredient_df"]
    uom_df = master_data["uom_df"]
    po_df = master_data["po_df"]
    poi_df = master_data["poi_df"]

    forecasts = forecast_results["forecasts"]
    forecast_dates = forecast_results["forecast_dates"][:risk_horizon]
    latest_date = forecast_results["latest_date"]
    forecast_start_date = latest_date + pd.Timedelta(days=1)

    # Unit maps
    uom_code_map = uom_df.set_index("id")["code"].to_dict()
    uom_name_map = uom_df.set_index("id")["name"].to_dict()

    # Incoming verified POs
    from replenishment_engine import get_verified_incoming_deliveries
    incoming_df = get_verified_incoming_deliveries(po_df, poi_df, forecast_start_date)

    # Preparation waste percentages
    prep_waste_map = get_ingredient_prep_waste_percentages(master_data, base_dir=base_dir)

    # Reconstruct active physical batches
    all_active_batches = get_active_ingredient_batches(
        simulated_stock_df, gri_df, gr_df, snapshot_date=latest_date
    )

    base_summary_df = replenishment_metrics["summary_df"]
    base_summary_map = base_summary_df.set_index("ingredient_id").to_dict("index")

    # Authoritative historical lead-time lookup by ingredient_id from full_lead_time_summary.csv
    lead_df = master_data.get("lead_df")
    if lead_df is None or lead_df.empty:
        lead_csv = (base_dir / "lead_time_outputs" / "full_lead_time_summary.csv") if base_dir else Path("lead_time_outputs/full_lead_time_summary.csv")
        if lead_csv.exists():
            lead_df = pd.read_csv(lead_csv)
        else:
            lead_df = pd.DataFrame()

    lead_time_display_map = {}
    if lead_df is not None and not lead_df.empty and "ingredient_id" in lead_df.columns and "avg_full_lead_time_days" in lead_df.columns:
        for _, l_row in lead_df.iterrows():
            try:
                l_id = int(l_row["ingredient_id"])
                val = l_row["avg_full_lead_time_days"]
                if pd.notna(val) and str(val).strip() != "":
                    num_val = float(val)
                    if not math.isnan(num_val):
                        lead_time_display_map[l_id] = str(int(round(num_val)))
            except (ValueError, TypeError):
                continue

    daily_forecast_rows = []
    reorder_recommendation_rows = []
    technical_summary_rows = []
    fefo_trajectories = {}

    for _, ing_row in ingredient_df.iterrows():
        ing_id = int(ing_row["id"])
        ing_name = ing_row["name"]
        shelf_life_days = ing_row.get("shelf_life_days", np.nan)
        base_uom_id = int(ing_row["base_uom_id"])
        base_uom_code = uom_code_map.get(base_uom_id, "")
        ing_display_name = f"{ing_name} ({base_uom_code})"

        base_meta = base_summary_map.get(ing_id, {})
        current_stock = float(base_meta.get("current_stock", 0.0))
        lead_time_days = float(base_meta.get("lead_time_days", 2.0))
        safety_stock = float(base_meta.get("safety_stock", 0.0))
        base_recommended_order = float(base_meta.get("recommended_order_qty", 0.0))
        base_stockout_day = base_meta.get("days_to_stockout")
        base_stockout_date = base_meta.get("stockout_date")

        # Authoritative historical lead time for display (rounded to nearest whole day, "N/A" if missing)
        lead_time_display = lead_time_display_map.get(ing_id, "N/A")

        batches = all_active_batches.get(ing_id, [])
        forecast_series = forecasts.get(
            ing_id, pd.Series([0.0] * risk_horizon, index=forecast_dates)
        ).iloc[:risk_horizon]

        prep_info = prep_waste_map.get(ing_id, {})
        prep_waste_pct = prep_info.get("prep_waste_pct", 0.0)

        # Usable stock at snapshot: batches with expiry_date >= forecast_start_date
        d1_norm = pd.to_datetime(forecast_dates[0]).normalize()
        usable_stock_start = sum(
            float(b["batch_stock"]) for b in batches if b["expiry_date"] >= d1_norm
        )
        expired_at_start = sum(
            float(b["batch_stock"]) for b in batches if b["expiry_date"] < d1_norm
        )

        # Average unit cost from actual receipts
        total_batch_stock = sum(float(b["batch_stock"]) for b in batches)
        avg_unit_cost = (
            sum(b["batch_stock"] * b["unit_cost"] for b in batches) / total_batch_stock
            if total_batch_stock > 0
            else 0.0
        )

        # Run FEFO simulation
        fefo_res = simulate_fefo_trajectory(
            batches,
            forecast_series,
            incoming_df,
            ing_id,
            lead_time_days,
            prep_waste_pct=prep_waste_pct,
            unit_cost_fallback=avg_unit_cost
        )
        fefo_trajectories[ing_id] = fefo_res
        traj_df = fefo_res["trajectory_df"]

        # -------------------------------------------------------------
        # Reorder Recommendation (Expiry-Aware & Baseline)
        # -------------------------------------------------------------
        coverage_days = lead_time_days + review_period
        cov_ceil = min(risk_horizon, int(math.ceil(coverage_days)))
        cov_traj = traj_df.iloc[:cov_ceil]

        # Forecast Requirement over coverage window (demand + prep waste)
        d_full = int(math.floor(coverage_days))
        d_frac = coverage_days - d_full
        if d_full < risk_horizon:
            full_req = float(traj_df.iloc[:d_full]["total_requirement"].sum())
            frac_req = float(d_frac * traj_df.iloc[d_full]["total_requirement"]) if d_full < len(traj_df) else 0.0
            cov_requirement = full_req + frac_req
        else:
            cov_requirement = float(traj_df.iloc[:risk_horizon]["total_requirement"].sum())

        # Expiry waste occurring within coverage window
        waste_in_coverage = float(cov_traj["expiring_qty"].sum())

        # Usable stock at expected delivery day ceil(L_i)
        usable_at_delivery = float(fefo_res["usable_stock_at_delivery"])

        # Eligible incoming deliveries within coverage window
        cov_end_date = forecast_dates[0] + pd.Timedelta(days=cov_ceil)
        ing_incoming = incoming_df[incoming_df["ingredient_id"] == ing_id] if not incoming_df.empty else pd.DataFrame()
        if not ing_incoming.empty:
            eligible_incoming = float(ing_incoming[ing_incoming["expected_date"] <= cov_end_date]["pending_qty"].sum())
        else:
            eligible_incoming = 0.0

        # Expiry-Adjusted Reorder Quantity
        # Effective usable stock deducts unconsumed stock that expires within the coverage window
        # Q_adj = max(0, Coverage Requirement + SS - (Effective Usable Stock + Eligible Incoming))
        effective_stock = max(0.0, usable_stock_start - waste_in_coverage)
        q_adj_raw = max(0.0, cov_requirement + safety_stock - (effective_stock + eligible_incoming))
        q_adj_recommended = round(q_adj_raw, 2)

        # Determine Reorder Status:
        # - "Reorder Required" if logic recommends reordering (q_adj_recommended > 0)
        # - "No Reorder Required" if logic does not recommend reordering (q_adj_recommended == 0)
        # - "Unknown" if required inputs or recommendation are unavailable
        base_risk_status = base_meta.get("risk_status")
        if (
            not base_meta
            or base_risk_status == "Unknown"
            or lead_time_display == "N/A"
            or q_adj_recommended is None
            or pd.isna(q_adj_recommended)
        ):
            reorder_status = "Unknown"
        elif q_adj_recommended > 0:
            reorder_status = "Reorder Required"
        else:
            reorder_status = "No Reorder Required"

        # -------------------------------------------------------------
        # Table A: Daily Demand & Spoilage Forecast (1 row per date)
        # Columns:
        # 1. Date
        # 2. Ingredient
        # 3. Lead Time (Days)
        # 4. Reorder Status
        # 5. Shelf Life
        # 6. Current Usable Stock
        # 7. Next-Day Demand
        # 8. Daily Forecast Demand
        # 9. Estimated Preparation Waste
        # 10. Days Until Expiry
        # 11. Expiring Quantity
        # 12. Projected Usable Stock
        # 13. Unmet Demand
        # -------------------------------------------------------------
        next_day_demand_val = fefo_res["next_day_demand"]
        shelf_life_str = (
            f"{int(shelf_life_days)} days"
            if (pd.notna(shelf_life_days) and str(shelf_life_days).strip() != "")
            else "N/A"
        )

        for _, trow in traj_df.iterrows():
            daily_forecast_rows.append({
                "Date": trow["date_str"],
                "Ingredient": ing_display_name,
                "Lead Time (Days)": lead_time_display,
                "Reorder Status": reorder_status,
                "Shelf Life": shelf_life_str,
                "Current Usable Stock": round(usable_stock_start, 2),
                "Next-Day Demand": round(next_day_demand_val, 2),
                "Daily Forecast Demand": round(trow["daily_forecast_demand"], 2),
                "Estimated Preparation Waste": round(trow["estimated_prep_waste"], 2),
                "Days Until Expiry": trow["days_until_expiry_str"],
                "Expiring Quantity": round(trow["expiring_qty"], 2),
                "Projected Usable Stock": round(trow["projected_usable_stock"], 2),
                "Unmet Demand": round(trow["unmet_demand"], 2),
                # Internal metadata for optional filtering
                "_ingredient_id": ing_id,
                "_ingredient_name": ing_name,
                "_uom_code": base_uom_code,
                "_shelf_life_days": shelf_life_days,
                "_lead_time_days_display": lead_time_display,
                "_reorder_status": reorder_status,
                "_days_until_expiry": trow["days_until_expiry"],
                "_has_spoilage_or_shortage": (trow["expiring_qty"] > 0 or trow["unmet_demand"] > 0),
            })

        # -------------------------------------------------------------
        # Table B: Expiry-Aware Reorder Recommendations
        # Columns:
        # 1. Ingredient
        # 2. Usable Stock at Expected Delivery
        # 3. Forecast Requirement
        # 4. Expected Expiry Waste
        # 5. Recommended Order Quantity
        # (+ Baseline Recommended Order side-by-side)
        # -------------------------------------------------------------
        reorder_recommendation_rows.append({
            "Ingredient": ing_display_name,
            "Usable Stock at Expected Delivery": round(usable_at_delivery, 2),
            "Forecast Requirement": round(cov_requirement, 2),
            "Expected Expiry Waste": round(waste_in_coverage, 2),
            "Baseline Recommended Order": round(base_recommended_order, 2),
            "Recommended Order Quantity": round(q_adj_recommended, 2),
            # Metadata for audit/filters
            "_ingredient_id": ing_id,
            "_ingredient_name": ing_name,
            "_lead_time_days": lead_time_days,
            "_lead_time_display": lead_time_display,
            "_reorder_status": reorder_status,
            "_safety_stock": safety_stock,
            "_order_difference": round(q_adj_recommended - base_recommended_order, 2),
        })


        # -------------------------------------------------------------
        # Technical Summary (for expander)
        # -------------------------------------------------------------
        nearest_batch = min(batches, key=lambda x: x["expiry_date"]) if batches else None
        nearest_expiry_str = nearest_batch["expiry_date"].strftime("%Y-%m-%d") if nearest_batch else "No Batches"
        days_to_nearest = (nearest_batch["expiry_date"] - latest_date).days if nearest_batch else np.nan

        fefo_stockout_day = fefo_res["stockout_day"]
        early_stockout = False
        if fefo_stockout_day is not None:
            if base_stockout_day is None or fefo_stockout_day < base_stockout_day:
                early_stockout = True

        technical_summary_rows.append({
            "ingredient_id": ing_id,
            "ingredient_name": ing_name,
            "unit": base_uom_code,
            "shelf_life_days": shelf_life_days,
            "current_physical_stock": round(current_stock, 2),
            "current_usable_stock": round(usable_stock_start, 2),
            "active_batch_count": len(batches),
            "nearest_expiry_date": nearest_expiry_str,
            "days_to_nearest_expiry": days_to_nearest,
            "prep_waste_pct": prep_waste_pct,
            "prep_waste_source": prep_info.get("source", ""),
            "total_expiry_waste_qty": fefo_res["total_expiry_waste_qty"],
            "total_expiry_waste_cost": fefo_res["total_expiry_waste_cost"],
            "waste_in_coverage_qty": round(waste_in_coverage, 2),
            "total_unmet_demand": fefo_res["total_unmet_demand"],
            "base_stockout_day": base_stockout_day,
            "fefo_stockout_day": fefo_stockout_day,
            "early_stockout_accelerated": early_stockout,
            "base_recommended_order": base_recommended_order,
            "expiry_adjusted_order": q_adj_recommended,
            "batches": batches,
        })

    daily_forecast_df = pd.DataFrame(daily_forecast_rows)
    reorder_df = pd.DataFrame(reorder_recommendation_rows)
    tech_df = pd.DataFrame(technical_summary_rows)

    # Aggregates
    total_spoilage_qty = round(tech_df["total_expiry_waste_qty"].sum(), 2)
    total_spoilage_cost = round(tech_df["total_expiry_waste_cost"].sum(), 2)
    ingredients_with_spoilage = int((tech_df["total_expiry_waste_qty"] > 0).sum())
    accelerated_stockouts_count = int(tech_df["early_stockout_accelerated"].sum())

    return {
        "daily_forecast_df": daily_forecast_df,
        "reorder_df": reorder_df,
        "technical_summary_df": tech_df,
        "fefo_trajectories": fefo_trajectories,
        "all_active_batches": all_active_batches,
        "prep_waste_map": prep_waste_map,
        "total_spoilage_qty": total_spoilage_qty,
        "total_spoilage_cost": total_spoilage_cost,
        "ingredients_with_spoilage": ingredients_with_spoilage,
        "accelerated_stockouts_count": accelerated_stockouts_count,
        "forecast_dates": forecast_dates,
        "latest_date": latest_date,
    }


def get_recipe_wastage_comparison(master_data: Dict[str, Any], base_dir: Optional[Path] = None) -> pd.DataFrame:
    """
    Extract recipe wastage_percent parameters alongside historical recorded waste
    to clearly audit preparation waste vs recorded expiry waste.
    """
    if base_dir is None:
        base_dir = Path(__file__).parent

    data_dir = base_dir / "data-rms" / "data-rms"
    clean_dir = base_dir / "DataCleaned"

    ri_file = data_dir / "recipe_ingredient.csv"
    ing_file = data_dir / "ingredient.csv"
    uom_file = data_dir / "unit_of_measure.csv"
    sle_file = data_dir / "stock_ledger_entry.csv"

    if not ri_file.exists() or not ing_file.exists():
        return pd.DataFrame()

    ri = pd.read_csv(ri_file)
    ing = pd.read_csv(ing_file)
    uom = pd.read_csv(uom_file)
    uom_map = uom.set_index("id")["code"].to_dict()

    # Aggregate recipe wastage percent per ingredient
    prep_stats = ri.groupby("ingredient_id").agg(
        min_wastage_pct=("wastage_percent", "min"),
        max_wastage_pct=("wastage_percent", "max"),
        avg_wastage_pct=("wastage_percent", "mean"),
        recipe_usage_count=("wastage_percent", "count")
    ).reset_index()

    # Historical recorded expiry waste from stock ledger
    if sle_file.exists():
        sle = pd.read_csv(sle_file)
        w_sle = sle[sle["movement_type"] == "WASTAGE"].copy()
        hist_waste = w_sle.groupby("ingredient_id").agg(
            historical_expiry_waste_qty=("qty_base", lambda x: round(abs(x.sum()), 2)),
            historical_expiry_waste_events=("id", "count"),
            historical_expiry_waste_cost=("total_cost", lambda x: round(x.sum(), 2))
        ).reset_index()
    else:
        hist_waste = pd.DataFrame(columns=[
            "ingredient_id", "historical_expiry_waste_qty",
            "historical_expiry_waste_events", "historical_expiry_waste_cost"
        ])

    merged = ing.merge(prep_stats, left_on="id", right_on="ingredient_id", how="left")
    merged = merged.merge(hist_waste, on="ingredient_id", how="left")

    merged["base_uom_code"] = merged["base_uom_id"].map(uom_map)
    merged["min_wastage_pct"] = merged["min_wastage_pct"].round(2)
    merged["max_wastage_pct"] = merged["max_wastage_pct"].round(2)
    merged["avg_wastage_pct"] = merged["avg_wastage_pct"].round(2)
    merged["historical_expiry_waste_qty"] = merged["historical_expiry_waste_qty"].fillna(0.0)
    merged["historical_expiry_waste_events"] = merged["historical_expiry_waste_events"].fillna(0).astype(int)
    merged["historical_expiry_waste_cost"] = merged["historical_expiry_waste_cost"].fillna(0.0)

    return merged[[
        "id", "name", "base_uom_code", "shelf_life_days",
        "avg_wastage_pct", "min_wastage_pct", "max_wastage_pct", "recipe_usage_count",
        "historical_expiry_waste_qty", "historical_expiry_waste_cost", "historical_expiry_waste_events"
    ]].rename(columns={
        "id": "Ingredient ID",
        "name": "Ingredient",
        "base_uom_code": "Unit",
        "shelf_life_days": "Shelf Life (d)",
        "avg_wastage_pct": "Avg Recipe Trim %",
        "min_wastage_pct": "Min Recipe Trim %",
        "max_wastage_pct": "Max Recipe Trim %",
        "recipe_usage_count": "Recipe Uses",
        "historical_expiry_waste_qty": "Total Recorded Expiry Waste (Qty)",
        "historical_expiry_waste_cost": "Total Recorded Expiry Cost (₹)",
        "historical_expiry_waste_events": "Expiry Waste Events"
    })
