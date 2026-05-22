"""
rules_engine_google_health.py
Evaluation logic for all 23 Google Health controls.
Returns ControlResult(status, what, why) per control.
H021/H022/H023 are manual — hardcoded OK with a reviewer note.
H022 uses Tab 40 + Tab 34 (available in new export).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

from config import ControlResult, STATUS_OK, STATUS_FLAG, STATUS_PARTIAL
from config_google_health import WHY, SCORING_EXCLUDED
from reader_databricks_google import (
    GoogleContext, get_sheet, find_col, to_float, to_str, clean_text,
    pct_str, money_str, num_str,
)

MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _yoy_row(df: pd.DataFrame, metric_name: str) -> Optional[dict]:
    """Extract a row from the Yearly KPIs key-value table by metric name."""
    col = find_col(df, ["metric", "Metric"])
    if col is None:
        return None
    for _, row in df.iterrows():
        if str(row[col]).strip().lower() == metric_name.lower():
            return row.to_dict()
    return None


def _yoy_float(df: pd.DataFrame, metric_name: str) -> Optional[float]:
    row = _yoy_row(df, metric_name)
    if row is None:
        return None
    yoy_col = find_col(pd.DataFrame([row]), ["YoY", "yoy"])
    if yoy_col is None:
        # positional fallback: 4th column (index 3)
        vals = list(row.values())
        return to_float(vals[3]) if len(vals) > 3 else None
    return to_float(row.get(yoy_col))


def _yoy_this(df: pd.DataFrame, metric_name: str) -> Optional[float]:
    row = _yoy_row(df, metric_name)
    if row is None:
        return None
    col = find_col(pd.DataFrame([row]), ["ThisPeriod", "this_period", "current"])
    if col is None:
        vals = list(row.values())
        return to_float(vals[1]) if len(vals) > 1 else None
    raw = str(row.get(col, "")).replace("$", "").replace(",", "").replace("%", "").strip()
    return to_float(raw)


def _yoy_prev(df: pd.DataFrame, metric_name: str) -> Optional[float]:
    row = _yoy_row(df, metric_name)
    if row is None:
        return None
    col = find_col(pd.DataFrame([row]), ["PreviousPeriod", "previous_period", "prior"])
    if col is None:
        vals = list(row.values())
        return to_float(vals[2]) if len(vals) > 2 else None
    raw = str(row.get(col, "")).replace("$", "").replace(",", "").replace("%", "").strip()
    return to_float(raw)


def _l3m_trend(df: pd.DataFrame, value_col_candidates: List[str]) -> Optional[List[dict]]:
    """Return last 3 completed months sorted ascending from L24M tab."""
    month_col = find_col(df, ["Month", "month"])
    val_col = find_col(df, value_col_candidates)
    if month_col is None or val_col is None:
        return None
    rows = []
    for _, row in df.iterrows():
        m = pd.to_datetime(str(row[month_col]), errors="coerce")
        v = to_float(row[val_col])
        if pd.isna(m) or v is None:
            continue
        rows.append({"month": m, "value": v})
    if not rows:
        return None
    rows.sort(key=lambda x: x["month"])
    # exclude current partial month if window_end is mid-month
    # just take the last 3 by date
    return rows[-3:] if len(rows) >= 3 else rows


def _monthly_budget(cs_row: pd.Series, window_end: Optional[date]) -> Optional[float]:
    """Return the month-specific budget if available, else fall back to Monthly_Budget__c."""
    if window_end is None:
        return to_float(cs_row.iloc[35]) if len(cs_row) > 35 else None
    month_idx = {1: 53, 2: 54, 3: 55, 4: 56, 5: 57, 6: 58,
                 7: 59, 8: 60, 9: 61, 10: 62, 11: 63, 12: 64}
    m = window_end.month
    col_i = month_idx.get(m)
    if col_i and len(cs_row) > col_i:
        v = to_float(cs_row.iloc[col_i])
        if v and v > 0:
            return v
    # fallback to Monthly_Budget__c col 35
    return to_float(cs_row.iloc[35]) if len(cs_row) > 35 else None


# ── Control evaluators ────────────────────────────────────────────────────────

def _h001(ctx: GoogleContext) -> ControlResult:
    """ROAS vs Target"""
    df02 = get_sheet(ctx, "DATE_RANGE_KPIS")
    df22 = get_sheet(ctx, "CLIENT_SUCCESS")
    if df02.empty or df22.empty:
        return ControlResult(STATUS_FLAG, "Data missing — Tab 02 or Tab 22 not found.", WHY["H001"])

    spend_col = find_col(df02, ["AdSpend"])
    sales_col = find_col(df02, ["AdSales"])
    if spend_col is None or sales_col is None:
        return ControlResult(STATUS_FLAG, "AdSpend or AdSales column not found in Tab 02.", WHY["H001"])

    row02 = df02.iloc[0]
    spend = to_float(row02[spend_col])
    sales = to_float(row02[sales_col])
    if not spend or not sales or spend == 0:
        return ControlResult(STATUS_FLAG, "Spend or AdSales is zero — ROAS cannot be calculated.", WHY["H001"])

    actual_roas = sales / spend

    cs_row = df22.iloc[0]
    # Primary_Spend_KPI__c col 74, acos col 75
    kpi_type = to_str(cs_row.iloc[74]) if len(cs_row) > 74 else ""
    acos_target = to_float(cs_row.iloc[75]) if len(cs_row) > 75 else None

    if acos_target and acos_target > 0:
        target_roas = 1.0 / acos_target
    else:
        return ControlResult(
            STATUS_PARTIAL,
            f"Actual ROAS = {actual_roas:.2f}x. No target ROAS found in Salesforce — cannot compare vs goal.",
            WHY["H001"],
        )

    delta_pct = (actual_roas - target_roas) / target_roas
    if delta_pct >= -0.05:
        status = STATUS_OK
    elif delta_pct >= -0.20:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Actual ROAS = {actual_roas:.2f}x vs target {target_roas:.2f}x ({delta_pct*100:+.1f}% to goal).",
        WHY["H001"],
    )


def _h002(ctx: GoogleContext) -> ControlResult:
    """Spend Pacing vs Monthly Budget"""
    df02 = get_sheet(ctx, "DATE_RANGE_KPIS")
    df22 = get_sheet(ctx, "CLIENT_SUCCESS")
    if df02.empty or df22.empty:
        return ControlResult(STATUS_FLAG, "Data missing — Tab 02 or Tab 22 not found.", WHY["H002"])

    spend_col = find_col(df02, ["AdSpend"])
    if spend_col is None:
        return ControlResult(STATUS_FLAG, "AdSpend column not found.", WHY["H002"])

    actual_spend = to_float(df02.iloc[0][spend_col])
    if actual_spend is None:
        return ControlResult(STATUS_FLAG, "AdSpend value is missing.", WHY["H002"])

    cs_row = df22.iloc[0]
    monthly_budget = _monthly_budget(cs_row, ctx.window_end)
    if not monthly_budget or monthly_budget == 0:
        return ControlResult(STATUS_PARTIAL, f"Actual spend = {money_str(actual_spend)}. No monthly budget found in Salesforce.", WHY["H002"])

    # Prorate budget to window days
    window_days = ctx.window_days or 30
    prorated = monthly_budget * (window_days / 30.0)
    pacing_pct = actual_spend / prorated

    if 0.90 <= pacing_pct <= 1.10:
        status = STATUS_OK
    elif 0.80 <= pacing_pct <= 1.15:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Spend pacing at {pacing_pct*100:.1f}% of prorated budget ({money_str(actual_spend)} actual vs {money_str(prorated)} expected over {window_days} days).",
        WHY["H002"],
    )


def _h003(ctx: GoogleContext) -> ControlResult:
    """Revenue (AdSales) YoY"""
    df = get_sheet(ctx, "YEARLY_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 03 not found or no data.", WHY["H003"])

    yoy = _yoy_float(df, "AdSales")
    curr = _yoy_this(df, "AdSales")
    prev = _yoy_prev(df, "AdSales")

    if yoy is None:
        return ControlResult(STATUS_FLAG, "AdSales YoY row not found in Tab 03.", WHY["H003"])

    if yoy >= -0.05:
        status = STATUS_OK
    elif yoy >= -0.20:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    curr_s = money_str(curr) if curr else "N/A"
    prev_s = money_str(prev) if prev else "N/A"
    return ControlResult(status, f"AdSales changed {yoy*100:+.1f}% YoY ({prev_s} → {curr_s}).", WHY["H003"])


def _h004(ctx: GoogleContext) -> ControlResult:
    """Orders / Conversions YoY"""
    df = get_sheet(ctx, "YEARLY_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 03 not found or no data.", WHY["H004"])

    yoy = _yoy_float(df, "Orders")
    curr = _yoy_this(df, "Orders")
    prev = _yoy_prev(df, "Orders")

    if yoy is None:
        return ControlResult(STATUS_FLAG, "Orders YoY row not found in Tab 03.", WHY["H004"])

    if yoy >= -0.05:
        status = STATUS_OK
    elif yoy >= -0.20:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    curr_s = num_str(curr, 0) if curr else "N/A"
    prev_s = num_str(prev, 0) if prev else "N/A"
    return ControlResult(status, f"Orders changed {yoy*100:+.1f}% YoY ({prev_s} → {curr_s}).", WHY["H004"])


def _h005(ctx: GoogleContext) -> ControlResult:
    """ACoS Trend YoY"""
    df = get_sheet(ctx, "YEARLY_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 03 not found or no data.", WHY["H005"])

    yoy = _yoy_float(df, "ACoS")
    curr = _yoy_this(df, "ACoS")
    prev = _yoy_prev(df, "ACoS")

    if yoy is None:
        return ControlResult(STATUS_FLAG, "ACoS YoY row not found in Tab 03.", WHY["H005"])

    # For ACoS, negative YoY = improvement
    if yoy <= 0.05:
        status = STATUS_OK
    elif yoy <= 0.15:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    curr_s = pct_str(curr) if curr else "N/A"
    prev_s = pct_str(prev) if prev else "N/A"
    delta_pp = (curr - prev) * 100 if curr and prev else None
    pp_str = f"{delta_pp:+.1f}pp" if delta_pp is not None else f"{yoy*100:+.1f}%"
    return ControlResult(status, f"ACoS changed {pp_str} YoY ({prev_s} → {curr_s}).", WHY["H005"])


def _h006(ctx: GoogleContext) -> ControlResult:
    """CPC Trend YoY"""
    df = get_sheet(ctx, "YEARLY_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 03 not found or no data.", WHY["H006"])

    yoy = _yoy_float(df, "CPC")
    curr = _yoy_this(df, "CPC")
    prev = _yoy_prev(df, "CPC")

    if yoy is None:
        return ControlResult(STATUS_FLAG, "CPC YoY row not found in Tab 03.", WHY["H006"])

    if yoy <= 0.10:
        status = STATUS_OK
    elif yoy <= 0.25:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    curr_s = money_str(curr) if curr else "N/A"
    prev_s = money_str(prev) if prev else "N/A"
    return ControlResult(status, f"CPC changed {yoy*100:+.1f}% YoY ({prev_s} → {curr_s}).", WHY["H006"])


def _h007(ctx: GoogleContext) -> ControlResult:
    """CTR Trend YoY"""
    df = get_sheet(ctx, "YEARLY_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 03 not found or no data.", WHY["H007"])

    yoy = _yoy_float(df, "CTR")
    curr = _yoy_this(df, "CTR")
    prev = _yoy_prev(df, "CTR")

    if yoy is None:
        return ControlResult(STATUS_FLAG, "CTR YoY row not found in Tab 03.", WHY["H007"])

    if yoy >= -0.10:
        status = STATUS_OK
    elif yoy >= -0.25:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    curr_s = pct_str(curr) if curr else "N/A"
    prev_s = pct_str(prev) if prev else "N/A"
    return ControlResult(status, f"CTR changed {yoy*100:+.1f}% YoY ({prev_s} → {curr_s}).", WHY["H007"])


def _h008(ctx: GoogleContext) -> ControlResult:
    """Conversion Rate Trend YoY"""
    df = get_sheet(ctx, "YEARLY_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 03 not found or no data.", WHY["H008"])

    yoy = _yoy_float(df, "CR")
    curr = _yoy_this(df, "CR")
    prev = _yoy_prev(df, "CR")

    if yoy is None:
        return ControlResult(STATUS_FLAG, "CR YoY row not found in Tab 03.", WHY["H008"])

    if yoy >= -0.10:
        status = STATUS_OK
    elif yoy >= -0.25:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    curr_s = pct_str(curr) if curr else "N/A"
    prev_s = pct_str(prev) if prev else "N/A"
    return ControlResult(status, f"CVR changed {yoy*100:+.1f}% YoY ({prev_s} → {curr_s}).", WHY["H008"])


def _h009(ctx: GoogleContext) -> ControlResult:
    """MoM Revenue Trend (L3M)"""
    df = get_sheet(ctx, "L24M_MONTHLY")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 04 not found or no data.", WHY["H009"])

    months = _l3m_trend(df, ["AdSales", "AdSales_sum", "Sales"])
    if not months or len(months) < 2:
        return ControlResult(STATUS_FLAG, "Not enough monthly data to compute L3M trend.", WHY["H009"])

    parts = [f"{MONTH_NAMES.get(m['month'].month, '?')}: {money_str(m['value'])}" for m in months]
    values = [m["value"] for m in months]
    declining = all(values[i] > values[i+1] for i in range(len(values)-1))
    flat = abs(values[-1] - values[0]) / max(abs(values[0]), 1) < 0.05

    if declining and len(months) == 3:
        status = STATUS_FLAG
        direction = "3 consecutive months declining"
    elif flat:
        status = STATUS_PARTIAL
        direction = "flat trend"
    else:
        status = STATUS_OK
        direction = "improving or mixed trend"

    return ControlResult(status, f"L3M revenue trend — {', '.join(parts)}. {direction}.", WHY["H009"])


def _h010(ctx: GoogleContext) -> ControlResult:
    """MoM ACoS Trend (L3M)"""
    df = get_sheet(ctx, "L24M_MONTHLY")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 04 not found or no data.", WHY["H010"])

    months = _l3m_trend(df, ["ACoS", "acos"])
    if not months or len(months) < 2:
        return ControlResult(STATUS_FLAG, "Not enough monthly data to compute L3M ACoS trend.", WHY["H010"])

    parts = [f"{MONTH_NAMES.get(m['month'].month, '?')}: {pct_str(m['value'])}" for m in months]
    values = [m["value"] for m in months]
    rising = all(values[i] < values[i+1] for i in range(len(values)-1))

    if rising and len(months) == 3:
        status = STATUS_FLAG
        direction = "3 consecutive months rising"
    elif rising:
        status = STATUS_PARTIAL
        direction = "rising trend"
    else:
        status = STATUS_OK
        direction = "stable or improving"

    return ControlResult(status, f"L3M ACoS trend — {', '.join(parts)}. {direction}.", WHY["H010"])


def _h011(ctx: GoogleContext) -> ControlResult:
    """PMAX Shopping Spend Share"""
    df = get_sheet(ctx, "PMAX_CHANNELS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 18 (PMAX Channels) not found or no data.", WHY["H011"])

    ft_col = find_col(df, ["FieldType", "fieldtype", "field_type"])
    cost_col = find_col(df, ["Cost", "cost", "Spend"])
    if ft_col is None or cost_col is None:
        return ControlResult(STATUS_FLAG, "FieldType or Cost column not found in Tab 18.", WHY["H011"])

    total = sum(to_float(r[cost_col]) or 0 for _, r in df.iterrows())
    if total == 0:
        return ControlResult(STATUS_FLAG, "Total PMAX spend is zero — cannot compute channel distribution.", WHY["H011"])

    shopping = sum(to_float(r[cost_col]) or 0 for _, r in df.iterrows()
                   if "SHOPPING" in str(r[ft_col]).upper())
    shopping_pct = shopping / total

    if shopping_pct >= 0.60:
        status = STATUS_OK
    elif shopping_pct >= 0.40:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Shopping represents {shopping_pct*100:.1f}% of total PMAX spend ({money_str(shopping)} of {money_str(total)}).",
        WHY["H011"],
    )


def _h012(ctx: GoogleContext) -> ControlResult:
    """Channel Type Mix"""
    df = get_sheet(ctx, "CHANNEL_TYPE")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 07 (Campaigns by Channel Type) not found or no data.", WHY["H012"])

    ch_col  = find_col(df, ["AdvertisingChannelType", "channel_type", "ChannelType"])
    sp_col  = find_col(df, ["Perc_Spend", "perc_spend", "Spend_pct"])
    spd_col = find_col(df, ["Spend", "spend", "Cost"])
    if ch_col is None or spd_col is None:
        return ControlResult(STATUS_FLAG, "Channel type or spend column not found in Tab 07.", WHY["H012"])

    total_spend = sum(to_float(r[spd_col]) or 0 for _, r in df.iterrows())
    channel_pcts = {}
    for _, row in df.iterrows():
        ch = str(row[ch_col]).upper()
        spd = to_float(row[spd_col]) or 0
        pct = (spd / total_spend) if total_spend > 0 else 0
        channel_pcts[ch] = pct

    pmax = channel_pcts.get("PERFORMANCE_MAX", 0)
    search = channel_pcts.get("SEARCH", 0)
    shopping = channel_pcts.get("SHOPPING", 0)

    if pmax > 0.85 and search < 0.05:
        status = STATUS_FLAG
    elif pmax > 0.70 and search < 0.10:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    return ControlResult(
        status,
        f"Channel mix — PMAX: {pmax*100:.1f}%, Search: {search*100:.1f}%, Shopping: {shopping*100:.1f}% of total spend.",
        WHY["H012"],
    )


def _h013(ctx: GoogleContext) -> ControlResult:
    """Zero-Spend Active Campaign Rate"""
    df13 = get_sheet(ctx, "CAMPAIGN_GOLD")
    df38 = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df13.empty:
        return ControlResult(STATUS_FLAG, "Tab 13 (Campaign Gold Metrics) not found or no data.", WHY["H013"])

    camp_col = find_col(df13, ["CampaignId", "campaign_id"])
    cost_col = find_col(df13, ["Cost", "cost", "Spend"])
    if camp_col is None or cost_col is None:
        return ControlResult(STATUS_FLAG, "CampaignId or Cost column not found in Tab 13.", WHY["H013"])

    spend_by_camp = df13.groupby(camp_col)[cost_col].sum().reset_index()
    spend_by_camp.columns = ["CampaignId", "TotalCost"]

    # Get active campaigns from settings tab if available
    active_camps = None
    if not df38.empty:
        status_col = find_col(df38, ["Status", "status"])
        camp38_col = find_col(df38, ["CampaignId", "campaign_id"])
        if status_col and camp38_col:
            active_camps = set(
                str(r[camp38_col]) for _, r in df38.iterrows()
                if str(r[status_col]).upper() == "ENABLED"
            )

    if active_camps is not None:
        active_df = spend_by_camp[spend_by_camp["CampaignId"].astype(str).isin(active_camps)]
    else:
        # fallback: all campaigns with any record
        active_df = spend_by_camp

    total_active = len(active_df)
    zero_spend = len(active_df[active_df["TotalCost"].fillna(0) == 0])

    if total_active == 0:
        return ControlResult(STATUS_FLAG, "No active campaigns found.", WHY["H013"])

    zero_pct = zero_spend / total_active

    if zero_pct <= 0.10:
        status = STATUS_OK
    elif zero_pct <= 0.25:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"{zero_spend} of {total_active} active campaigns ({zero_pct*100:.1f}%) recorded zero spend in the window.",
        WHY["H013"],
    )


def _h014(ctx: GoogleContext) -> ControlResult:
    """Price Competitiveness Score"""
    df = get_sheet(ctx, "PRICE_COMPETITIVENESS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Price competitiveness data not available for this account.", WHY["H014"])

    price_col = find_col(df, ["price"])
    bench_col = find_col(df, ["benchmark_price"])
    gap_col   = find_col(df, ["price_gap_perc", "price_gap"])

    if price_col is None or bench_col is None:
        return ControlResult(STATUS_PARTIAL, "Price or benchmark_price column not found in Tab 20.", WHY["H014"])

    valid = df[df[bench_col].notna() & (df[bench_col] != 0)]
    total = len(valid)
    if total == 0:
        return ControlResult(STATUS_PARTIAL, "No products with benchmark pricing data found.", WHY["H014"])

    above = sum(1 for _, r in valid.iterrows()
                if (to_float(r[price_col]) or 0) > (to_float(r[bench_col]) or 0))
    above_pct = above / total

    if above_pct <= 0.20:
        status = STATUS_OK
    elif above_pct <= 0.40:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"{above} of {total} products ({above_pct*100:.1f}%) are priced above the benchmark price.",
        WHY["H014"],
    )


def _h015(ctx: GoogleContext) -> ControlResult:
    """Top 5 Products Revenue Concentration"""
    df = get_sheet(ctx, "PRODUCT_SHOPPING")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 08 (Product Shopping Report) not found or no data.", WHY["H015"])

    sales_col = find_col(df, ["Sales", "AdSales", "ConversionValue"])
    if sales_col is None:
        return ControlResult(STATUS_FLAG, "Sales column not found in Tab 08.", WHY["H015"])

    df_s = df.copy()
    df_s["_sales"] = df_s[sales_col].apply(to_float).fillna(0)
    total_sales = df_s["_sales"].sum()
    if total_sales == 0:
        return ControlResult(STATUS_FLAG, "Total product sales is zero.", WHY["H015"])

    top5 = df_s.nlargest(5, "_sales")["_sales"].sum()
    top5_pct = top5 / total_sales

    if top5_pct <= 0.60:
        status = STATUS_OK
    elif top5_pct <= 0.80:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Top 5 products represent {top5_pct*100:.1f}% of total AdSales ({money_str(top5)} of {money_str(total_sales)}).",
        WHY["H015"],
    )


def _h016(ctx: GoogleContext) -> ControlResult:
    """Device Performance Split"""
    df = get_sheet(ctx, "DEVICE_BREAKDOWN")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 16 (Device Breakdown) not found or no data.", WHY["H016"])

    dev_col   = find_col(df, ["Device", "device"])
    spend_col = find_col(df, ["Spend", "Cost", "spend"])
    orders_col = find_col(df, ["Orders", "Conversions"])
    sales_col = find_col(df, ["Sales", "AdSales"])

    if dev_col is None or spend_col is None:
        return ControlResult(STATUS_FLAG, "Device or Spend column not found in Tab 16.", WHY["H016"])

    results = {}
    for _, row in df.iterrows():
        dev = str(row[dev_col]).upper()
        spd = to_float(row[spend_col]) or 0
        sal = to_float(row[sales_col]) if sales_col else None
        results[dev] = {"spend": spd, "roas": (sal / spd) if sal and spd > 0 else None}

    parts = []
    for dev, vals in results.items():
        roas_s = f"ROAS {vals['roas']:.2f}x" if vals["roas"] else "no sales"
        parts.append(f"{dev.title()}: spend {money_str(vals['spend'])}, {roas_s}")

    mobile = results.get("MOBILE", {})
    desktop = results.get("DESKTOP", {})
    mobile_roas = mobile.get("roas")
    desktop_roas = desktop.get("roas")
    mobile_spend = mobile.get("spend", 0)
    total_spend = sum(v["spend"] for v in results.values()) or 1
    mobile_share = mobile_spend / total_spend

    if mobile_roas and desktop_roas and mobile_spend > 0:
        if mobile_share > 0.40 and mobile_roas < desktop_roas * 0.50:
            status = STATUS_FLAG
        elif mobile_share > 0.30 and mobile_roas < desktop_roas * 0.70:
            status = STATUS_PARTIAL
        else:
            status = STATUS_OK
    else:
        status = STATUS_PARTIAL

    return ControlResult(status, " | ".join(parts) + ".", WHY["H016"])


def _h017(ctx: GoogleContext) -> ControlResult:
    """Billing Status"""
    df = get_sheet(ctx, "STRIPE_INFO")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 15 (Stripe & Account Info) not found.", WHY["H017"])

    row = df.iloc[0]
    status_val = to_str(row.iloc[13]) if len(row) > 13 else ""
    invoice_status = to_str(row.iloc[22]) if len(row) > 22 else ""
    last_payment = to_str(row.iloc[23]) if len(row) > 23 else ""

    billing_active = status_val.lower() == "active"
    invoice_ok = invoice_status.lower() in ("paid", "active", "")

    if billing_active and invoice_ok:
        status = STATUS_OK
    elif billing_active:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Billing status = {status_val or 'unknown'}. Invoice status = {invoice_status or 'unknown'}. Last payment = {last_payment or 'unknown'}.",
        WHY["H017"],
    )


def _h018(ctx: GoogleContext) -> ControlResult:
    """Churn Risk Signal"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 (Client Success) not found.", WHY["H018"])

    row = df.iloc[0]
    csm_risk   = to_str(row.iloc[68]) if len(row) > 68 else ""
    cust_risk  = to_str(row.iloc[28]) if len(row) > 28 else ""
    risk_score = to_float(row.iloc[70]) if len(row) > 70 else None

    high_risk_terms = {"high", "red", "critical", "flag", "at risk"}
    csm_flagged  = any(t in csm_risk.lower() for t in high_risk_terms)
    cust_flagged = any(t in cust_risk.lower() for t in high_risk_terms)

    if csm_flagged or cust_flagged:
        status = STATUS_FLAG
    elif risk_score is not None and risk_score > 7:
        status = STATUS_FLAG
    elif risk_score is not None and risk_score > 4:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    score_s = num_str(risk_score, 0) if risk_score is not None else "N/A"
    return ControlResult(
        status,
        f"CSM Churn Risk = {csm_risk or 'not set'}. Customer Risk = {cust_risk or 'not set'}. Account Risk Score = {score_s}.",
        WHY["H018"],
    )


def _h019(ctx: GoogleContext) -> ControlResult:
    """QR Score"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 (Client Success) not found.", WHY["H019"])

    row = df.iloc[0]
    past_qr    = to_float(row.iloc[3])  if len(row) > 3  else None
    current_qr = to_float(row.iloc[72]) if len(row) > 72 else None

    score = current_qr or past_qr
    if score is None:
        return ControlResult(STATUS_PARTIAL, "No QR Score found in Salesforce.", WHY["H019"])

    if score >= 8:
        status = STATUS_OK
    elif score >= 6:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    past_s = num_str(past_qr, 1) if past_qr else "N/A"
    curr_s = num_str(current_qr, 1) if current_qr else "N/A"
    return ControlResult(status, f"Most Recent QR Score = {past_s}. Current QR Score = {curr_s}.", WHY["H019"])


def _h020(ctx: GoogleContext) -> ControlResult:
    """MRR vs Monthly Budget Ratio"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 (Client Success) not found.", WHY["H020"])

    row = df.iloc[0]
    mrr    = to_float(row.iloc[32]) if len(row) > 32 else None
    budget = to_float(row.iloc[35]) if len(row) > 35 else None

    if not mrr or not budget or budget == 0:
        return ControlResult(STATUS_PARTIAL, f"MRR = {money_str(mrr)}. Monthly budget = {money_str(budget)}. Cannot compute ratio.", WHY["H020"])

    fee_pct = mrr / budget

    if fee_pct <= 0.15:
        status = STATUS_OK
    elif fee_pct <= 0.25:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"MRR = {money_str(mrr)} vs monthly budget = {money_str(budget)}. Fee ratio = {fee_pct*100:.1f}% of managed budget.",
        WHY["H020"],
    )


def _h021(ctx: GoogleContext) -> ControlResult:
    """Conversion Tag Health — MANUAL"""
    return ControlResult(
        STATUS_OK,
        "Manual review required. Verify conversion tag status in Google Ads: Tools > Conversions.",
        WHY["H021"],
    )


def _h022(ctx: GoogleContext) -> ControlResult:
    """GMC + GA4 Connection — uses Tab 40 and Tab 34"""
    df40 = get_sheet(ctx, "ACCOUNT_LINKS")
    df34 = get_sheet(ctx, "ADVERTISER_DETAILS")

    gmc_linked = None
    ga4_linked = None
    merchant_id = None

    # Tab 34 has GMC_Linked directly
    if not df34.empty:
        gmc_col = find_col(df34, ["GMC_Linked", "gmc_linked"])
        mid_col = find_col(df34, ["MerchantID", "merchant_id"])
        if gmc_col:
            gmc_linked = str(df34.iloc[0][gmc_col]).lower() in ("true", "1", "yes")
        if mid_col:
            merchant_id = to_str(df34.iloc[0][mid_col])

    # Tab 40 has MerchantStatus and AnalyticsStatus
    if not df40.empty:
        merch_col    = find_col(df40, ["MerchantStatus", "merchant_status"])
        analyt_col   = find_col(df40, ["AnalyticsStatus", "analytics_status"])
        analyt_id    = find_col(df40, ["AnalyticsId", "analytics_id"])

        row40 = df40.iloc[0]
        if gmc_linked is None and merch_col:
            merch_val = to_str(row40[merch_col])
            gmc_linked = merch_val.lower() not in ("false", "0", "no", "")

        if analyt_col:
            analyt_val = to_str(row40[analyt_col])
            ga4_linked = analyt_val.lower() not in ("false", "0", "no", "")
        if analyt_id:
            aid = to_str(row40[analyt_id])
            if aid and aid.lower() not in ("nan", "false", "0", ""):
                ga4_linked = True

    if gmc_linked is None and ga4_linked is None:
        return ControlResult(STATUS_PARTIAL, "Account link data not found. Manual check required in Google Ads Linked Accounts.", WHY["H022"])

    gmc_s = "linked" if gmc_linked else "NOT linked"
    ga4_s = "linked" if ga4_linked else "NOT linked"
    mid_s = f" (Merchant ID: {merchant_id})" if merchant_id else ""

    if gmc_linked and ga4_linked:
        status = STATUS_OK
    elif gmc_linked or ga4_linked:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(status, f"GMC = {gmc_s}{mid_s}. GA4 = {ga4_s}.", WHY["H022"])


def _h023(ctx: GoogleContext) -> ControlResult:
    """Product Disapproval Rate — MANUAL"""
    return ControlResult(
        STATUS_OK,
        "Manual review required. Check GMC: Overview > Products Dashboard for disapproval rate.",
        WHY["H023"],
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

_EVALUATORS = {
    "H001": _h001, "H002": _h002, "H003": _h003, "H004": _h004,
    "H005": _h005, "H006": _h006, "H007": _h007, "H008": _h008,
    "H009": _h009, "H010": _h010, "H011": _h011, "H012": _h012,
    "H013": _h013, "H014": _h014, "H015": _h015, "H016": _h016,
    "H017": _h017, "H018": _h018, "H019": _h019, "H020": _h020,
    "H021": _h021, "H022": _h022, "H023": _h023,
}


def evaluate_all_health(ctx: GoogleContext) -> Dict[str, ControlResult]:
    results = {}
    for cid, fn in _EVALUATORS.items():
        try:
            results[cid] = fn(ctx)
        except Exception as e:
            results[cid] = ControlResult(
                STATUS_FLAG,
                f"Evaluation error: {e}",
                "Internal error — review this control manually.",
            )
    return results
