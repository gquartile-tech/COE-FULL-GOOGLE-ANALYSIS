"""
rules_engine_google_strategy.py
Strategy is reviewer-driven — controls document campaign structure presence only.
No automated scoring thresholds per architecture spec.
"""
from __future__ import annotations

import re
from typing import Dict

import pandas as pd

from config import ControlResult, STATUS_OK, STATUS_FLAG, STATUS_PARTIAL
from config_google_strategy import WHY
from reader_databricks_google import (
    GoogleContext, get_sheet, find_col, to_float, to_str, money_str,
)


def _campaign_names(ctx: GoogleContext) -> list:
    """Return all campaign names across enriched + settings tabs."""
    names = []
    for key in ["CAMPAIGNS_V2_ENRICHED", "CAMPAIGN_SETTINGS", "CAMPAIGN_GOLD"]:
        df = get_sheet(ctx, key)
        if not df.empty:
            col = find_col(df, ["CampaignName", "campaign_name"])
            if col:
                names.extend(df[col].dropna().astype(str).tolist())
    return list(set(names))


def _spend_map(ctx: GoogleContext) -> dict:
    df = get_sheet(ctx, "CAMPAIGN_GOLD")
    if df.empty:
        return {}
    cid = find_col(df, ["CampaignId"])
    cost = find_col(df, ["Cost", "cost"])
    name = find_col(df, ["CampaignName"])
    if not cid or not cost:
        return {}
    return {to_str(r[cid]): {"cost": to_float(r[cost]) or 0, "name": to_str(r[name]) if name else ""}
            for _, r in df.iterrows()}


def _find_campaign(names: list, patterns: list, spend_map: dict = None) -> tuple:
    """Return (found: bool, campaign_name: str, spend: float)"""
    for name in names:
        for pat in patterns:
            if re.search(pat, name, re.IGNORECASE):
                spend = 0
                if spend_map:
                    for cid, info in spend_map.items():
                        if info.get("name") == name:
                            spend = info.get("cost", 0)
                return True, name, spend
    return False, "", 0


def _s001(ctx): return _campaign_check(ctx, ["S001"], [r'\b(EE|Catchall|Catch.All|Everything.Else|General)\b'], "Catchall/EE")
def _s002(ctx): return _campaign_check(ctx, ["S002"], [r'\b(Top.Products?|TopProducts?|Best.Sellers?)\b'], "Top Products")
def _s003(ctx): return _campaign_check(ctx, ["S003"], [r'\b(Price.?Tier|Margin|High.?Margin|Low.?Margin)\b'], "Price Tier/Margin")
def _s004(ctx): return _campaign_check(ctx, ["S004"], [r'\b(Brand(ed)?|TM)\b'], "Branded Shopping/PMAX")
def _s005(ctx): return _campaign_check(ctx, ["S005"], [r'\b(Suppression|Suppress)\b'], "Shopping Suppression")
def _s006(ctx): return _campaign_check(ctx, ["S006"], [r'\b(ProductType|Product.?Type|Category)\b'], "Product Type")
def _s007(ctx): return _campaign_check(ctx, ["S007"], [r'\b(Zombie)\b'], "Zombie")
def _s008(ctx): return _campaign_check(ctx, ["S008"], [r'\b(Remnant)\b'], "Remnant")
def _s009(ctx): return _campaign_check(ctx, ["S009"], [r'\b(Query.?Based|QB|QueryBased)\b'], "Query-Based")
def _s010(ctx): return _campaign_check(ctx, ["S010"], [r'\b(TM|Search.TM|Branded|Brand|SKW)\b'], "Branded Search TM", require_search=True)
def _s011(ctx): return _campaign_check(ctx, ["S011"], [r'\b(NB|NonBrand|Non.Brand|Search.NB)\b'], "NB Search", require_search=True)
def _s012(ctx): return _campaign_check(ctx, ["S012"], [r'\b(DSA|Dynamic.Search)\b'], "DSA")


def _campaign_check(ctx: GoogleContext, cids: list, patterns: list, label: str, require_search: bool = False) -> ControlResult:
    cid = cids[0]
    names = _campaign_names(ctx)
    sm = _spend_map(ctx)

    # Filter by search channel if required
    if require_search:
        search_names = []
        df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
        if not df.empty:
            ch_col = find_col(df, ["AdvertisingChannelType"])
            nm_col = find_col(df, ["CampaignName"])
            if ch_col and nm_col:
                search_names = [to_str(r[nm_col]) for _, r in df.iterrows()
                                if "SEARCH" in to_str(r[ch_col]).upper()]
        names = search_names or names

    found, camp_name, spend = _find_campaign(names, patterns, sm)

    if found:
        spend_s = f" Spend: {money_str(spend)}." if spend > 0 else " No spend recorded in window."
        return ControlResult(STATUS_OK, f"{label} campaign detected: '{camp_name}'.{spend_s}", WHY[cid])
    return ControlResult(STATUS_FLAG, f"No {label} campaign found. Review campaign structure with strategist.", WHY[cid])


def _s013(ctx: GoogleContext) -> ControlResult:
    """Match Type Strategy"""
    df = get_sheet(ctx, "KEYWORD_REPORT")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Keyword report not found.", WHY["S013"])

    mt_col = find_col(df, ["MatchType"])
    if not mt_col:
        return ControlResult(STATUS_PARTIAL, "MatchType column not found.", WHY["S013"])

    counts = df[mt_col].astype(str).str.upper().value_counts()
    total = counts.sum()
    if total == 0:
        return ControlResult(STATUS_FLAG, "No keywords found.", WHY["S013"])

    exact_pct = counts.get("EXACT", 0) / total
    broad_pct = counts.get("BROAD", 0) / total
    phrase_pct = counts.get("PHRASE", 0) / total

    return ControlResult(
        STATUS_OK,
        f"Match type distribution — EXACT: {exact_pct*100:.1f}%, BROAD: {broad_pct*100:.1f}%, PHRASE: {phrase_pct*100:.1f}%. Total keywords: {total}. Reviewer to assess intentionality.",
        WHY["S013"],
    )


def _s014(ctx: GoogleContext) -> ControlResult:
    """Device Bid Adjustments Applied"""
    df = get_sheet(ctx, "DEVICE_BREAKDOWN")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Device breakdown not found.", WHY["S014"])

    dev_col  = find_col(df, ["Device"])
    spd_col  = find_col(df, ["Spend"])
    sal_col  = find_col(df, ["Sales"])
    if not dev_col or not spd_col:
        return ControlResult(STATUS_PARTIAL, "Device or Spend column not found.", WHY["S014"])

    roas_by_dev = {}
    for _, row in df.iterrows():
        dev = to_str(row[dev_col]).upper()
        spd = to_float(row[spd_col]) or 0
        sal = to_float(row[sal_col]) if sal_col else 0
        roas_by_dev[dev] = (sal / spd) if sal and spd > 0 else None

    parts = ", ".join(f"{k}: {v:.2f}x" if v else f"{k}: no data" for k, v in roas_by_dev.items())
    mobile = roas_by_dev.get("MOBILE")
    desktop = roas_by_dev.get("DESKTOP")

    if mobile and desktop and abs(mobile - desktop) / max(desktop, 0.01) > 0.30:
        msg = f"Material ROAS difference by device detected — {parts}. Device bid adjustments should be reviewed."
        return ControlResult(STATUS_PARTIAL, msg, WHY["S014"])
    return ControlResult(STATUS_OK, f"Device ROAS — {parts}. Reviewer to confirm bid adjustments are applied.", WHY["S014"])


def _s015(ctx: GoogleContext) -> ControlResult:
    """Demographic Segmentation"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    product_type = ""
    if not df.empty and len(df.iloc[0]) > 24:
        product_type = to_str(df.iloc[0].iloc[24])

    return ControlResult(
        STATUS_PARTIAL,
        f"Account product type = {product_type or 'not set'}. Demographic bid adjustments require manual verification in Google Ads Audiences > Demographics.",
        WHY["S015"],
    )


def _s016(ctx: GoogleContext) -> ControlResult:
    """Location Bid Adjustments"""
    df = get_sheet(ctx, "LOCATION_PERF")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Location performance data not available.", WHY["S016"])

    region_col = find_col(df, ["State", "Region"])
    cost_col   = find_col(df, ["Cost"])
    conv_col   = find_col(df, ["Conversions"])
    if not region_col or not cost_col:
        return ControlResult(STATUS_PARTIAL, "Region or Cost not found in Tab 26.", WHY["S016"])

    grouped = df.groupby(region_col).agg(
        total_cost=(cost_col, "sum"),
        total_conv=(conv_col, "sum") if conv_col else (cost_col, "count")
    ).reset_index()

    total_spend = grouped["total_cost"].sum()
    top3 = grouped.nlargest(3, "total_cost")
    top3_names = ", ".join(top3[region_col].astype(str).tolist())
    top3_spend_pct = top3["total_cost"].sum() / total_spend * 100 if total_spend > 0 else 0

    return ControlResult(
        STATUS_PARTIAL,
        f"Top 3 locations by spend: {top3_names} ({top3_spend_pct:.1f}% of total). Location bid adjustment configuration requires manual verification in Google Ads.",
        WHY["S016"],
    )


def _s017(ctx: GoogleContext) -> ControlResult:
    """Campaign Budget Allocation Optimized"""
    df = get_sheet(ctx, "CAMPAIGN_GOLD")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 13 not found.", WHY["S017"])

    cost_col  = find_col(df, ["Cost"])
    sales_col = find_col(df, ["AdSales"])
    cid_col   = find_col(df, ["CampaignId"])
    name_col  = find_col(df, ["CampaignName"])
    if not cost_col or not cid_col:
        return ControlResult(STATUS_FLAG, "Cost or CampaignId not found in Tab 13.", WHY["S017"])

    agg = df.groupby(cid_col).agg(
        total_cost=(cost_col, "sum"),
        total_sales=(sales_col, "sum") if sales_col else (cost_col, "count"),
        name=(name_col, "first") if name_col else (cost_col, "count")
    ).reset_index()

    agg["roas"] = agg.apply(lambda r: r["total_sales"] / r["total_cost"] if r["total_cost"] > 0 else 0, axis=1)
    total_spend = agg["total_cost"].sum()
    top3_by_roas = agg.nlargest(3, "roas")
    top3_spend_pct = top3_by_roas["total_cost"].sum() / total_spend * 100 if total_spend > 0 else 0

    return ControlResult(
        STATUS_OK,
        f"Top 3 campaigns by ROAS represent {top3_spend_pct:.1f}% of total spend. Reviewer to confirm budget is intentionally concentrated on highest-ROAS campaigns.",
        WHY["S017"],
    )


def _s018(ctx: GoogleContext) -> ControlResult:
    """PMAX vs Search vs Shopping Spend Balance"""
    df = get_sheet(ctx, "CHANNEL_TYPE")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 07 not found.", WHY["S018"])

    ch_col  = find_col(df, ["AdvertisingChannelType"])
    spd_col = find_col(df, ["Spend"])
    pct_col = find_col(df, ["Perc_Spend"])
    if not ch_col:
        return ControlResult(STATUS_FLAG, "AdvertisingChannelType not found.", WHY["S018"])

    total = sum(to_float(r[spd_col]) or 0 for _, r in df.iterrows()) if spd_col else 0
    pcts = {}
    for _, row in df.iterrows():
        ch = to_str(row[ch_col]).upper()
        if pct_col:
            pct = to_float(row[pct_col]) or 0
        elif spd_col and total > 0:
            pct = (to_float(row[spd_col]) or 0) / total
        else:
            pct = 0
        pcts[ch] = pct

    pmax   = pcts.get("PERFORMANCE_MAX", 0)
    search = pcts.get("SEARCH", 0)
    shop   = pcts.get("SHOPPING", 0)

    return ControlResult(
        STATUS_OK,
        f"PMAX = {pmax*100:.1f}%, Search = {search*100:.1f}%, Shopping = {shop*100:.1f}% of total spend. Reviewer to assess if channel balance is intentional.",
        WHY["S018"],
    )


def _s019(ctx: GoogleContext) -> ControlResult:
    """Demand Gen Prospecting Campaign"""
    names = _campaign_names(ctx)
    df07 = get_sheet(ctx, "CHANNEL_TYPE")
    ch_col = find_col(df07, ["AdvertisingChannelType"]) if not df07.empty else None
    spd_col = find_col(df07, ["Spend"]) if not df07.empty else None

    # Check channel type tab for DEMAND_GEN
    dg_spend = 0
    if ch_col and spd_col:
        for _, row in df07.iterrows():
            if "DEMAND" in to_str(row[ch_col]).upper():
                dg_spend += to_float(row[spd_col]) or 0

    found, camp, spend = _find_campaign(names, [r'\b(DemandGen|Demand.Gen|Prospecting)\b'])

    if found or dg_spend > 0:
        return ControlResult(STATUS_OK, f"Demand Gen campaign detected: '{camp or 'DEMAND_GEN channel'}'. Spend: {money_str(max(spend, dg_spend))}.", WHY["S019"])
    return ControlResult(STATUS_FLAG, "No Demand Gen prospecting campaign found. Upper funnel may be underfunded.", WHY["S019"])


def _s020(ctx: GoogleContext) -> ControlResult:
    """Demand Gen Remarketing Campaign"""
    names = _campaign_names(ctx)
    found, camp, spend = _find_campaign(names, [r'\b(Remarketing|Retargeting|RLSA)\b'])

    if found:
        spend_s = money_str(spend) if spend > 0 else "no spend in window"
        return ControlResult(STATUS_OK, f"Remarketing campaign detected: '{camp}'. Spend: {spend_s}.", WHY["S020"])
    return ControlResult(STATUS_FLAG, "No remarketing or retargeting campaign found.", WHY["S020"])


def _s021(ctx):
    return ControlResult(STATUS_OK, "Manual review required. Verify Optimized Targeting is disabled in Google Ads Display/Demand Gen campaigns > Ad Groups > Audiences.", WHY["S021"])


_EVALUATORS = {
    "S001": _s001, "S002": _s002, "S003": _s003, "S004": _s004, "S005": _s005,
    "S006": _s006, "S007": _s007, "S008": _s008, "S009": _s009, "S010": _s010,
    "S011": _s011, "S012": _s012, "S013": _s013, "S014": _s014, "S015": _s015,
    "S016": _s016, "S017": _s017, "S018": _s018, "S019": _s019, "S020": _s020,
    "S021": _s021,
}


def evaluate_all_strategy(ctx: GoogleContext) -> Dict[str, ControlResult]:
    results = {}
    for cid, fn in _EVALUATORS.items():
        try:
            results[cid] = fn(ctx)
        except Exception as e:
            results[cid] = ControlResult(STATUS_FLAG, f"Evaluation error: {e}", "Internal error — review manually.")
    return results
