"""
rules_engine_google_mastery.py
Evaluation logic for all 14 Google Mastery controls.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Optional

import pandas as pd

from config import ControlResult, STATUS_OK, STATUS_FLAG, STATUS_PARTIAL
from config_google_mastery import WHY
from reader_databricks_google import (
    GoogleContext, get_sheet, find_col, to_float, to_str, clean_text,
    money_str, pct_str, num_str, _parse_date,
)


def _m001(ctx: GoogleContext) -> ControlResult:
    """Meeting Frequency — last QR record in Client Success"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 not found.", WHY["M001"])

    date_col = find_col(df, ["CreatedDate", "created_date"])
    if date_col is None:
        return ControlResult(STATUS_FLAG, "CreatedDate column not found in Tab 22.", WHY["M001"])

    dates = [_parse_date(v) for v in df[date_col] if not pd.isna(v)]
    dates = [d for d in dates if d is not None]
    if not dates:
        return ControlResult(STATUS_FLAG, "No meeting dates found in Salesforce.", WHY["M001"])

    last = max(dates)
    ref = ctx.window_end or date.today()
    days_ago = (ref - last).days

    if days_ago <= 30:
        status = STATUS_OK
    elif days_ago <= 60:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(status, f"Last meeting recorded {last}. {days_ago} days since last meeting.", WHY["M001"])


def _m002(ctx: GoogleContext) -> ControlResult:
    """Touchpoint Frequency — SystemModstamp proxy"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Tab 22 not found. Manual Slack cadence check required.", WHY["M002"])

    mod_col = find_col(df, ["SystemModstamp", "system_modstamp", "LastModifiedDate"])
    if mod_col is None:
        return ControlResult(STATUS_PARTIAL, "SystemModstamp not found. Manual touchpoint check required.", WHY["M002"])

    dates = [_parse_date(v) for v in df[mod_col] if not pd.isna(v)]
    dates = [d for d in dates if d is not None]
    if not dates:
        return ControlResult(STATUS_PARTIAL, "No CS update timestamps found. Manual Slack cadence check required.", WHY["M002"])

    last = max(dates)
    ref = ctx.window_end or date.today()
    days_ago = (ref - last).days

    if days_ago <= 14:
        status = STATUS_OK
    elif days_ago <= 30:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Last CS record update: {last} ({days_ago} days ago). Note: this is a proxy — actual Slack cadence requires manual verification.",
        WHY["M002"],
    )


def _m003(ctx: GoogleContext) -> ControlResult:
    """Budgets & Goals Updated in Salesforce"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 not found.", WHY["M003"])

    row = df.iloc[0]
    budget    = to_float(row.iloc[35]) if len(row) > 35 else None
    kpi_type  = to_str(row.iloc[74])   if len(row) > 74 else ""

    issues = []
    if not budget or budget == 0:
        issues.append("Monthly Budget is missing or zero")
    if not kpi_type:
        issues.append("Primary Spend KPI is not set")

    if not issues:
        return ControlResult(
            STATUS_OK,
            f"Monthly Budget = {money_str(budget)}. Primary KPI = {kpi_type}.",
            WHY["M003"],
        )
    elif len(issues) == 1:
        return ControlResult(
            STATUS_PARTIAL,
            f"Monthly Budget = {money_str(budget)}. Primary KPI = {kpi_type or 'not set'}. Issue: {issues[0]}.",
            WHY["M003"],
        )
    else:
        return ControlResult(
            STATUS_FLAG,
            f"Issues found: {'; '.join(issues)}.",
            WHY["M003"],
        )


def _m004(ctx: GoogleContext) -> ControlResult:
    """Salesforce Profile ID Populated"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 not found.", WHY["M004"])

    row = df.iloc[0]
    sf_id  = to_str(row.iloc[80]) if len(row) > 80 else ""
    exp_id = ctx.account_id or ""

    if not sf_id:
        return ControlResult(STATUS_FLAG, f"AdvertiserId not found in Salesforce. Export AdvertiserId = {exp_id or 'unknown'}.", WHY["M004"])

    match = sf_id.strip() == exp_id.strip()
    if match:
        return ControlResult(STATUS_OK, f"AdvertiserId = {sf_id} matches export. Profile ID confirmed.", WHY["M004"])
    else:
        return ControlResult(STATUS_PARTIAL, f"AdvertiserId in CS = {sf_id}. Export ID = {exp_id}. Mismatch — verify correct account linked.", WHY["M004"])


def _m005(ctx: GoogleContext) -> ControlResult:
    """DPL Active"""
    df = get_sheet(ctx, "DPL_PERFORMANCE")
    if df.empty:
        return ControlResult(
            STATUS_FLAG,
            "DPL Performance tab (28) returned no data for this account. DPL may not be configured.",
            WHY["M005"],
        )

    row_count = len(df)
    return ControlResult(STATUS_OK, f"DPL Performance data found. {row_count} DPL records in window.", WHY["M005"])


def _m006(ctx: GoogleContext) -> ControlResult:
    """Custom Labels (min 2 managed by QT)"""
    df = get_sheet(ctx, "FEED_PRODUCTS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 30 (Feed Products) not found or no data.", WHY["M006"])

    label_cols = []
    for candidate in ["CustomLabel0", "CustomLabel1", "CustomLabel2", "CustomLabel3", "CustomLabel4",
                       "custom_label_0", "custom_label_1", "custom_label_2", "custom_label_3", "custom_label_4"]:
        col = find_col(df, [candidate])
        if col:
            label_cols.append(col)

    if not label_cols:
        return ControlResult(
            STATUS_FLAG,
            "Custom label columns (CustomLabel0–4) not found in Tab 30. Feed may not include custom labels.",
            WHY["M006"],
        )

    active_labels = []
    for col in label_cols:
        non_null = df[col].dropna()
        non_null = non_null[non_null.astype(str).str.strip() != ""]
        if len(non_null) > 0:
            sample = to_str(non_null.iloc[0])
            active_labels.append(f"{col}: '{sample}'")

    count = len(active_labels)
    if count >= 2:
        status = STATUS_OK
    elif count == 1:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    label_str = ", ".join(active_labels) if active_labels else "none populated"
    return ControlResult(status, f"{count} custom label(s) with data found. {label_str}.", WHY["M006"])


def _m007(ctx: GoogleContext) -> ControlResult:
    """Feed Transformers Active — proxy via title patterns"""
    df = get_sheet(ctx, "FEED_PRODUCTS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Tab 30 not found. Feed transformer check requires manual Portal verification.", WHY["M007"])

    title_col = find_col(df, ["Title", "title"])
    if title_col is None:
        return ControlResult(STATUS_PARTIAL, "Title column not found in Tab 30. Manual Portal check required.", WHY["M007"])

    total = len(df)
    if total == 0:
        return ControlResult(STATUS_PARTIAL, "No feed products found. Manual transformer check required.", WHY["M007"])

    # QT transformer signatures: check for QT or Quartile in title
    titles_lower = df[title_col].dropna().astype(str).str.lower()
    qt_pattern_count = (titles_lower.str.contains("quartile", regex=False) |
                        titles_lower.str.contains("qt_", regex=False)).sum()

    return ControlResult(
        STATUS_PARTIAL,
        f"{total} products in feed. {qt_pattern_count} titles contain QT/Quartile pattern. Manual QT Portal verification required to confirm transformer rules are active.",
        WHY["M007"],
    )


def _m008(ctx: GoogleContext) -> ControlResult:
    """Price Competitiveness Active"""
    df = get_sheet(ctx, "PRICE_COMPETITIVENESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Price competitiveness data (Tab 20) not available for this account.", WHY["M008"])

    bench_col = find_col(df, ["benchmark_price"])
    if bench_col is None:
        return ControlResult(STATUS_FLAG, "benchmark_price column not found in Tab 20.", WHY["M008"])

    total = len(df)
    with_bench = df[bench_col].notna().sum()
    pct = with_bench / total if total > 0 else 0

    if pct >= 0.50:
        status = STATUS_OK
    elif pct >= 0.20:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"{with_bench} of {total} products ({pct*100:.1f}%) have benchmark pricing data populated.",
        WHY["M008"],
    )


def _m009(ctx: GoogleContext) -> ControlResult:
    """Feed-Based Inventory Filters"""
    df = get_sheet(ctx, "FEED_PRODUCTS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 30 (Feed Products) not found.", WHY["M009"])

    avail_col = find_col(df, ["Availability", "availability"])
    cost_col  = find_col(df, ["cost"])

    if avail_col is None:
        return ControlResult(STATUS_PARTIAL, "Availability column not found in Tab 30. Manual inventory filter check required.", WHY["M009"])

    total = len(df)
    oos = df[avail_col].astype(str).str.lower().str.contains("out of stock").sum()

    spend_on_oos = 0
    if cost_col:
        oos_mask = df[avail_col].astype(str).str.lower().str.contains("out of stock")
        spend_on_oos = df.loc[oos_mask, cost_col].apply(to_float).fillna(0).sum()

    if oos == 0:
        status = STATUS_OK
        msg = f"No out-of-stock products found in feed. {total} total products."
    elif spend_on_oos > 0:
        status = STATUS_FLAG
        msg = f"{oos} out-of-stock product(s) found. {money_str(spend_on_oos)} spent on unavailable products."
    else:
        status = STATUS_PARTIAL
        msg = f"{oos} out-of-stock product(s) in feed. No spend detected on unavailable products."

    return ControlResult(status, msg, WHY["M009"])


def _m010(ctx: GoogleContext) -> ControlResult:
    """Product Types Configured"""
    df = get_sheet(ctx, "FEED_PRODUCTS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 30 not found.", WHY["M010"])

    pt_col = find_col(df, ["ProductType", "product_type", "ProductTypeL1"])
    if pt_col is None:
        return ControlResult(STATUS_FLAG, "ProductType column not found in Tab 30.", WHY["M010"])

    total = len(df)
    null_count = df[pt_col].isna().sum() + (df[pt_col].astype(str).str.strip() == "").sum()
    populated = total - null_count
    pct = populated / total if total > 0 else 0

    if pct >= 0.90:
        status = STATUS_OK
    elif pct >= 0.70:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"{populated} of {total} products ({pct*100:.1f}%) have ProductType populated.",
        WHY["M010"],
    )


def _m011(ctx: GoogleContext) -> ControlResult:
    """Brand Mapping Configured"""
    df = get_sheet(ctx, "FEED_PRODUCTS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 30 not found.", WHY["M011"])

    brand_col = find_col(df, ["Brand", "brand"])
    if brand_col is None:
        return ControlResult(STATUS_FLAG, "Brand column not found in Tab 30.", WHY["M011"])

    total = len(df)
    null_count = df[brand_col].isna().sum() + (df[brand_col].astype(str).str.strip() == "").sum()
    populated = total - null_count
    pct = populated / total if total > 0 else 0

    if pct >= 0.80:
        status = STATUS_OK
    elif pct >= 0.60:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"{populated} of {total} products ({pct*100:.1f}%) have Brand populated.",
        WHY["M011"],
    )


def _m012(ctx: GoogleContext) -> ControlResult:
    """Quartile Portal Connection"""
    df15 = get_sheet(ctx, "STRIPE_INFO")
    df22 = get_sheet(ctx, "CLIENT_SUCCESS")

    connected = None
    channel = ""

    if not df15.empty:
        conn_col = find_col(df15, ["IsConnect", "is_connect"])
        if conn_col:
            connected = str(df15.iloc[0][conn_col]).lower() in ("true", "1", "yes")

    if not df22.empty and len(df22.iloc[0]) > 79:
        channel = to_str(df22.iloc[0].iloc[79])

    if connected is None:
        return ControlResult(STATUS_PARTIAL, "IsConnect field not found. Manual Portal connection check required.", WHY["M012"])

    if connected:
        return ControlResult(STATUS_OK, f"Quartile portal connection = active. Platform channel = {channel or 'not specified'}.", WHY["M012"])
    else:
        return ControlResult(STATUS_FLAG, f"Quartile portal connection = NOT connected. Channel = {channel or 'unknown'}. TACoS reporting unavailable.", WHY["M012"])


def _m013(ctx: GoogleContext) -> ControlResult:
    """Account Segment Classification"""
    df15 = get_sheet(ctx, "STRIPE_INFO")
    df22 = get_sheet(ctx, "CLIENT_SUCCESS")

    segment = ""
    product_type = ""

    if not df15.empty and len(df15.iloc[0]) > 9:
        segment = to_str(df15.iloc[0].iloc[9])

    if not df22.empty and len(df22.iloc[0]) > 24:
        product_type = to_str(df22.iloc[0].iloc[24])

    if not segment and not product_type:
        return ControlResult(STATUS_FLAG, "Segment and product classification not found. Check Salesforce and Stripe records.", WHY["M013"])
    elif not segment or not product_type:
        return ControlResult(STATUS_PARTIAL, f"Customer Segment = {segment or 'not set'}. Product Classification = {product_type or 'not set'}. One field missing.", WHY["M013"])
    else:
        return ControlResult(STATUS_OK, f"Customer Segment = {segment}. Product Classification = {product_type}.", WHY["M013"])


def _m014(ctx: GoogleContext) -> ControlResult:
    """Primary Objective Documented"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 not found.", WHY["M014"])

    row = df.iloc[0]
    objective = clean_text(row.iloc[39]) if len(row) > 39 else ""
    context   = clean_text(row.iloc[38]) if len(row) > 38 else ""

    if not objective:
        return ControlResult(STATUS_FLAG, "Primary Objective is not documented in Salesforce.", WHY["M014"])
    elif not context:
        return ControlResult(STATUS_PARTIAL, f"Primary Objective = '{objective[:80]}'. Additional context is missing.", WHY["M014"])
    else:
        return ControlResult(STATUS_OK, f"Primary Objective = '{objective[:80]}'. Context documented.", WHY["M014"])


# ── Orchestrator ──────────────────────────────────────────────────────────────

_EVALUATORS = {
    "M001": _m001, "M002": _m002, "M003": _m003, "M004": _m004,
    "M005": _m005, "M006": _m006, "M007": _m007, "M008": _m008,
    "M009": _m009, "M010": _m010, "M011": _m011, "M012": _m012,
    "M013": _m013, "M014": _m014,
}


def evaluate_all_mastery(ctx: GoogleContext) -> Dict[str, ControlResult]:
    results = {}
    for cid, fn in _EVALUATORS.items():
        try:
            results[cid] = fn(ctx)
        except Exception as e:
            results[cid] = ControlResult(STATUS_FLAG, f"Evaluation error: {e}", "Internal error — review manually.")
    return results
