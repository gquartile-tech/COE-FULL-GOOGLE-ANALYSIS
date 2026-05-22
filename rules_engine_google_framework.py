"""
rules_engine_google_framework.py
Evaluation logic for all 42 Google Framework controls.
Manual controls return OK with a reviewer note.
All data-backed controls use Tab 38 (Campaign Settings) as primary campaign source
since it has the most complete campaign metadata.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

import pandas as pd

from config import ControlResult, STATUS_OK, STATUS_FLAG, STATUS_PARTIAL
from config_google_framework import WHY
from reader_databricks_google import (
    GoogleContext, get_sheet, find_col, to_float, to_str, clean_text,
    money_str, pct_str, num_str,
)

PROMO_PATTERN = re.compile(r'\b(sale|promo|holiday|black.?friday|cyber|bfcm|seasonal|clearance|discount)\b', re.IGNORECASE)
QT_PREFIX     = re.compile(r'^QT[_\-]', re.IGNORECASE)


def _active_campaigns(ctx: GoogleContext) -> pd.DataFrame:
    """Return ENABLED campaigns from Tab 38 Campaign Settings."""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return pd.DataFrame()
    status_col = find_col(df, ["Status", "status"])
    if status_col:
        return df[df[status_col].astype(str).str.upper() == "ENABLED"].copy()
    return df.copy()


def _spend_by_campaign(ctx: GoogleContext) -> dict:
    """Return {CampaignId: total_cost} from Tab 13."""
    df = get_sheet(ctx, "CAMPAIGN_GOLD")
    if df.empty:
        return {}
    cid = find_col(df, ["CampaignId", "campaign_id"])
    cost = find_col(df, ["Cost", "cost"])
    if not cid or not cost:
        return {}
    return df.groupby(cid)[cost].sum().to_dict()


# ── Controls ──────────────────────────────────────────────────────────────────

def _f001(ctx: GoogleContext) -> ControlResult:
    """Naming Convention Compliance"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 38 not found.", WHY["F001"])

    name_col   = find_col(df, ["CampaignName", "campaign_name"])
    status_col = find_col(df, ["Status", "status"])
    if not name_col:
        return ControlResult(STATUS_FLAG, "CampaignName column not found.", WHY["F001"])

    spend_map = _spend_by_campaign(ctx)
    active = df[df[status_col].astype(str).str.upper() == "ENABLED"] if status_col else df

    non_qt = []
    for _, row in active.iterrows():
        name = to_str(row[name_col])
        cid = to_str(row.get("CampaignId", ""))
        spend = spend_map.get(cid, 0) or 0
        if spend > 0 and not QT_PREFIX.match(name):
            non_qt.append(name)

    total_active = len(active)
    non_qt_count = len(non_qt)

    if non_qt_count == 0:
        status = STATUS_OK
    elif non_qt_count / max(total_active, 1) <= 0.10:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    sample = ", ".join(non_qt[:3])
    msg = (f"{non_qt_count} of {total_active} active campaigns with spend don't follow QT_ naming. "
           f"Examples: {sample}." if non_qt else f"All {total_active} active campaigns follow QT_ naming convention.")
    return ControlResult(status, msg, WHY["F001"])


def _f002(ctx: GoogleContext) -> ControlResult:
    """Legacy Campaign Cleanup"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 38 not found.", WHY["F002"])

    name_col   = find_col(df, ["CampaignName"])
    status_col = find_col(df, ["Status"])
    start_col  = find_col(df, ["StartDate", "start_date"])
    if not status_col or not start_col:
        return ControlResult(STATUS_PARTIAL, "Status or StartDate column not found. Manual legacy check required.", WHY["F002"])

    spend_map = _spend_by_campaign(ctx)
    ref = ctx.window_end or pd.Timestamp.now().date()
    legacy = []
    for _, row in df.iterrows():
        st = to_str(row[status_col]).upper()
        if st != "PAUSED":
            continue
        sd = pd.to_datetime(str(row[start_col]), errors="coerce")
        if pd.isna(sd):
            continue
        days_old = (pd.Timestamp(ref) - sd).days
        if days_old > 180:
            cid = to_str(row.get("CampaignId", ""))
            spend = spend_map.get(cid, 0) or 0
            if spend > 0:
                legacy.append(to_str(row[name_col]) if name_col else cid)

    if not legacy:
        return ControlResult(STATUS_OK, "No legacy paused campaigns with historical spend found.", WHY["F002"])
    elif len(legacy) <= 3:
        return ControlResult(STATUS_PARTIAL, f"{len(legacy)} paused campaign(s) with spend older than 180 days: {', '.join(legacy[:3])}.", WHY["F002"])
    else:
        return ControlResult(STATUS_FLAG, f"{len(legacy)} legacy paused campaigns with historical spend found. Examples: {', '.join(legacy[:3])}.", WHY["F002"])


def _f003(ctx: GoogleContext) -> ControlResult:
    """Auto-Apply Settings — proxy via bidding strategy"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Tab 38 not found. Manual auto-apply check required in Google Ads.", WHY["F003"])

    bid_col  = find_col(df, ["BiddingStrategyType", "bidding_strategy_type"])
    name_col = find_col(df, ["CampaignName"])
    st_col   = find_col(df, ["Status"])

    if not bid_col:
        return ControlResult(STATUS_PARTIAL, "BiddingStrategyType not found. Manual auto-apply check required.", WHY["F003"])

    active = df[df[st_col].astype(str).str.upper() == "ENABLED"] if st_col else df
    non_qt = []
    for _, row in active.iterrows():
        name = to_str(row[name_col]) if name_col else ""
        bst = to_str(row[bid_col]).upper()
        if not QT_PREFIX.match(name) and bst not in ("", "NAN"):
            non_qt.append(f"{name}: {bst}")

    if not non_qt:
        return ControlResult(STATUS_OK, "All active campaigns appear to follow QT governance patterns.", WHY["F003"])
    else:
        return ControlResult(STATUS_PARTIAL, f"{len(non_qt)} non-QT campaign(s) with active bid strategies. Manual auto-apply verification required. Examples: {', '.join(non_qt[:2])}.", WHY["F003"])


def _f004(ctx: GoogleContext) -> ControlResult:
    """Display Expansion Disabled on Search"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 38 not found.", WHY["F004"])

    ch_col   = find_col(df, ["AdvertisingChannelType"])
    net_col  = find_col(df, ["TargetContentNetwork"])
    st_col   = find_col(df, ["Status"])
    name_col = find_col(df, ["CampaignName"])
    if not ch_col or not net_col:
        return ControlResult(STATUS_PARTIAL, "Channel type or TargetContentNetwork not found.", WHY["F004"])

    active = df[df[st_col].astype(str).str.upper() == "ENABLED"] if st_col else df
    flagged = []
    for _, row in active.iterrows():
        ch = to_str(row[ch_col]).upper()
        net = to_str(row[net_col]).lower()
        if ch == "SEARCH" and net in ("true", "1"):
            name = to_str(row[name_col]) if name_col else "unknown"
            flagged.append(name)

    if not flagged:
        return ControlResult(STATUS_OK, "No Search campaigns have TargetContentNetwork enabled.", WHY["F004"])
    return ControlResult(STATUS_FLAG, f"{len(flagged)} Search campaign(s) have display expansion enabled: {', '.join(flagged[:3])}.", WHY["F004"])


def _f005(ctx: GoogleContext) -> ControlResult:
    """Location Targeting Mode — proxy via zero-conversion regions"""
    df = get_sheet(ctx, "LOCATION_PERF")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Tab 26 not found. Manual location targeting mode check required.", WHY["F005"])

    region_col = find_col(df, ["Region", "State", "region"])
    cost_col   = find_col(df, ["Cost", "cost"])
    conv_col   = find_col(df, ["Conversions", "conversions"])
    if not region_col or not cost_col:
        return ControlResult(STATUS_PARTIAL, "Region or Cost column not found in Tab 26. Manual check required.", WHY["F005"])

    grouped = df.groupby(region_col).agg(
        total_cost=(cost_col, "sum"),
        total_conv=(conv_col, "sum") if conv_col else (cost_col, "count")
    ).reset_index()

    total_spend = grouped["total_cost"].sum()
    zero_conv_regions = grouped[(grouped["total_cost"] > 0) & (grouped["total_conv"] == 0)]
    zero_conv_spend = zero_conv_regions["total_cost"].sum()
    pct = zero_conv_spend / total_spend if total_spend > 0 else 0

    if pct > 0.20:
        status = STATUS_FLAG
    elif pct > 0.05:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    return ControlResult(
        status,
        f"{len(zero_conv_regions)} region(s) with spend and zero conversions ({pct*100:.1f}% of total spend). Note: Location targeting mode (Presence vs Presence+Interest) requires manual verification in Google Ads campaign settings.",
        WHY["F005"],
    )


def _f006(ctx: GoogleContext) -> ControlResult:
    """Promotion End Dates"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Tab 38 not found.", WHY["F006"])

    name_col  = find_col(df, ["CampaignName"])
    start_col = find_col(df, ["StartDate"])
    st_col    = find_col(df, ["Status"])
    if not name_col or not start_col:
        return ControlResult(STATUS_PARTIAL, "CampaignName or StartDate not found.", WHY["F006"])

    active = df[df[st_col].astype(str).str.upper() == "ENABLED"] if st_col else df
    ref = ctx.window_end or pd.Timestamp.now().date()
    flagged = []
    for _, row in active.iterrows():
        name = to_str(row[name_col])
        if not PROMO_PATTERN.search(name):
            continue
        sd = pd.to_datetime(str(row[start_col]), errors="coerce")
        if not pd.isna(sd) and (pd.Timestamp(ref) - sd).days > 60:
            flagged.append(name)

    if not flagged:
        return ControlResult(STATUS_OK, "No active campaigns with promotional naming older than 60 days found.", WHY["F006"])
    return ControlResult(STATUS_FLAG, f"{len(flagged)} active campaign(s) with promo naming and start date > 60 days ago: {', '.join(flagged[:3])}.", WHY["F006"])


def _f007(ctx: GoogleContext) -> ControlResult:
    """PMAX Automation Settings — MANUAL"""
    return ControlResult(STATUS_OK, "Manual review required. Verify PMAX automation settings in Google Ads campaign settings.", WHY["F007"])


def _f008(ctx: GoogleContext) -> ControlResult:
    """Match Type Governance"""
    df = get_sheet(ctx, "KEYWORD_REPORT")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 09 (Keyword Report) not found or no data.", WHY["F008"])

    mt_col = find_col(df, ["MatchType", "match_type"])
    if not mt_col:
        return ControlResult(STATUS_FLAG, "MatchType column not found in Tab 09.", WHY["F008"])

    counts = df[mt_col].astype(str).str.upper().value_counts()
    total = counts.sum()
    if total == 0:
        return ControlResult(STATUS_FLAG, "No keywords found in Tab 09.", WHY["F008"])

    broad_pct = counts.get("BROAD", 0) / total
    exact_pct = counts.get("EXACT", 0) / total

    if exact_pct < 0.10 and broad_pct > 0.80:
        status = STATUS_FLAG
    elif exact_pct < 0.10:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    return ControlResult(
        status,
        f"Match type distribution — BROAD: {broad_pct*100:.1f}%, EXACT: {exact_pct*100:.1f}%, PHRASE: {counts.get('PHRASE',0)/total*100:.1f}%. Total keywords: {total}.",
        WHY["F008"],
    )


def _f009(ctx: GoogleContext) -> ControlResult:
    """TM Terms in QT Portal — proxy via branded keyword detection"""
    df = get_sheet(ctx, "KEYWORD_REPORT")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Keyword report not found. Manual TM terms portal check required.", WHY["F009"])

    kw_col = find_col(df, ["Keyword", "keyword"])
    camp_col = find_col(df, ["CampaignName"])
    if not kw_col:
        return ControlResult(STATUS_PARTIAL, "Keyword column not found. Manual portal check required.", WHY["F009"])

    # Look for TM/branded campaigns
    tm_keywords = []
    for _, row in df.iterrows():
        camp = to_str(row[camp_col]) if camp_col else ""
        if re.search(r'\b(TM|Search_TM|Branded|Brand)\b', camp, re.IGNORECASE):
            kw = to_str(row[kw_col])
            if kw:
                tm_keywords.append(kw)

    if tm_keywords:
        return ControlResult(STATUS_PARTIAL, f"{len(tm_keywords)} TM keywords detected in Search campaigns. Portal upload status requires manual verification. Sample: {', '.join(set(tm_keywords[:3]))}.", WHY["F009"])
    return ControlResult(STATUS_PARTIAL, "No TM keywords detected in Search campaigns. Manual QT Portal verification required.", WHY["F009"])


def _f010(ctx: GoogleContext) -> ControlResult:
    """Branded Search Campaign Active"""
    df = get_sheet(ctx, "CAMPAIGNS_V2_ENRICHED")
    if df.empty:
        df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Campaign data not found.", WHY["F010"])

    spend_map = _spend_by_campaign(ctx)
    name_col = find_col(df, ["CampaignName"])
    ch_col   = find_col(df, ["AdvertisingChannelType", "CampaignType"])
    cid_col  = find_col(df, ["CampaignId"])

    branded = []
    for _, row in df.iterrows():
        name = to_str(row[name_col]) if name_col else ""
        ch   = to_str(row[ch_col]).upper() if ch_col else ""
        cid  = to_str(row[cid_col]) if cid_col else ""
        if ch == "SEARCH" and re.search(r'\b(TM|Brand|Branded|SKW)\b', name, re.IGNORECASE):
            spend = spend_map.get(cid, 0) or 0
            branded.append((name, spend))

    if branded:
        best = max(branded, key=lambda x: x[1])
        return ControlResult(STATUS_OK, f"Branded Search campaign detected: '{best[0]}'. Spend in window: {money_str(best[1])}.", WHY["F010"])
    return ControlResult(STATUS_FLAG, "No branded/TM Search campaign found with spend in the window.", WHY["F010"])


def _f011(ctx: GoogleContext) -> ControlResult:
    """Non-Brand Search Campaign Active"""
    df = get_sheet(ctx, "CAMPAIGNS_V2_ENRICHED")
    if df.empty:
        df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Campaign data not found.", WHY["F011"])

    spend_map = _spend_by_campaign(ctx)
    name_col = find_col(df, ["CampaignName"])
    ch_col   = find_col(df, ["AdvertisingChannelType", "CampaignType"])
    cid_col  = find_col(df, ["CampaignId"])

    nb_camps = []
    for _, row in df.iterrows():
        name = to_str(row[name_col]) if name_col else ""
        ch   = to_str(row[ch_col]).upper() if ch_col else ""
        cid  = to_str(row[cid_col]) if cid_col else ""
        if ch == "SEARCH" and re.search(r'\b(NB|NonBrand|Non_Brand|DSA|Dynamic)\b', name, re.IGNORECASE):
            spend = spend_map.get(cid, 0) or 0
            nb_camps.append((name, spend))

    if nb_camps:
        best = max(nb_camps, key=lambda x: x[1])
        return ControlResult(STATUS_OK, f"Non-brand Search campaign: '{best[0]}'. Spend: {money_str(best[1])}.", WHY["F011"])
    return ControlResult(STATUS_FLAG, "No non-branded Search campaign found with spend.", WHY["F011"])


def _f012(ctx: GoogleContext) -> ControlResult:
    """Search Term Waste"""
    df11 = get_sheet(ctx, "SEARCH_TERMS")
    df02 = get_sheet(ctx, "DATE_RANGE_KPIS")
    if df11.empty:
        return ControlResult(STATUS_FLAG, "Tab 11 (Search Terms Report) not found.", WHY["F012"])

    term_col = find_col(df11, ["SearchTerm", "search_term"])
    cost_col = find_col(df11, ["Cost", "cost"])
    conv_col = find_col(df11, ["Conversions", "conversions"])
    if not term_col or not cost_col:
        return ControlResult(STATUS_FLAG, "SearchTerm or Cost column not found in Tab 11.", WHY["F012"])

    # Get avg CPC from Tab 02
    avg_cpc = 0.35  # default fallback
    if not df02.empty:
        cpc_col = find_col(df02, ["CPC", "cpc"])
        if cpc_col:
            avg_cpc = to_float(df02.iloc[0][cpc_col]) or 0.35

    threshold = avg_cpc * 3
    waste_terms = []
    total_search_spend = 0.0

    for _, row in df11.iterrows():
        cost = to_float(row[cost_col]) or 0
        total_search_spend += cost
        conv = to_float(row[conv_col]) if conv_col else 0
        if cost > threshold and (conv is None or conv == 0):
            waste_terms.append((to_str(row[term_col]), cost))

    waste_spend = sum(w[1] for w in waste_terms)
    pct = waste_spend / total_search_spend if total_search_spend > 0 else 0

    if pct < 0.05:
        status = STATUS_OK
    elif pct < 0.15:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"{len(waste_terms)} search term(s) with spend > avg CPC × 3 (${threshold:.2f}) and zero conversions. Waste spend: {money_str(waste_spend)} ({pct*100:.1f}% of total search spend).",
        WHY["F012"],
    )


def _f013(ctx: GoogleContext) -> ControlResult:
    """Negative Keyword Coverage"""
    df = get_sheet(ctx, "NEGATIVE_KEYWORDS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Negative keywords tab (31) not found or empty. Manual check required.", WHY["F013"])

    kw_col   = find_col(df, ["Keyword"])
    type_col = find_col(df, ["Type"])

    # Check for actual keyword negatives (not just demographic exclusions)
    if type_col:
        kw_types = df[type_col].astype(str).str.upper().unique()
        has_keyword_negatives = any(t in ("KEYWORD", "NEGATIVE_KEYWORD") for t in kw_types)
    else:
        has_keyword_negatives = False

    if kw_col:
        actual_kws = df[kw_col].dropna()
        actual_kws = actual_kws[actual_kws.astype(str).str.strip() != ""]
        kw_count = len(actual_kws)
    else:
        kw_count = 0

    if kw_count > 0:
        return ControlResult(STATUS_OK, f"{kw_count} negative keyword(s) found across campaigns.", WHY["F013"])
    elif has_keyword_negatives:
        return ControlResult(STATUS_PARTIAL, "Negative keyword records found but Keyword values are empty. Manual shared exclusion list check required.", WHY["F013"])
    else:
        return ControlResult(STATUS_PARTIAL, "Tab 31 contains only demographic exclusions (age/gender), not keyword negatives. Shared keyword exclusion lists require manual verification.", WHY["F013"])


def _f014(ctx: GoogleContext) -> ControlResult:
    """PMAX Bid Strategy"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 38 not found.", WHY["F014"])

    ch_col  = find_col(df, ["AdvertisingChannelType"])
    bid_col = find_col(df, ["BiddingStrategyType"])
    name_col = find_col(df, ["CampaignName"])
    st_col  = find_col(df, ["Status"])
    if not ch_col or not bid_col:
        return ControlResult(STATUS_PARTIAL, "Channel type or bidding strategy not found.", WHY["F014"])

    active = df[df[st_col].astype(str).str.upper() == "ENABLED"] if st_col else df
    pmax_manual = []
    for _, row in active.iterrows():
        if "PERFORMANCE_MAX" in to_str(row[ch_col]).upper():
            bst = to_str(row[bid_col]).upper()
            if "MANUAL_CPC" in bst:
                name = to_str(row[name_col]) if name_col else "unknown"
                pmax_manual.append(name)

    if not pmax_manual:
        return ControlResult(STATUS_OK, "No active PMAX campaigns using MANUAL_CPC. Bid strategy is compliant.", WHY["F014"])
    return ControlResult(STATUS_FLAG, f"{len(pmax_manual)} PMAX campaign(s) using MANUAL_CPC: {', '.join(pmax_manual[:3])}.", WHY["F014"])


def _f015(ctx: GoogleContext) -> ControlResult:
    """Shopping Bid Strategy"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 38 not found.", WHY["F015"])

    ch_col  = find_col(df, ["AdvertisingChannelType"])
    bid_col = find_col(df, ["BiddingStrategyType"])
    name_col = find_col(df, ["CampaignName"])
    st_col  = find_col(df, ["Status"])
    cid_col = find_col(df, ["CampaignId"])
    if not ch_col or not bid_col:
        return ControlResult(STATUS_PARTIAL, "Channel type or bidding strategy not found.", WHY["F015"])

    spend_map = _spend_by_campaign(ctx)
    active = df[df[st_col].astype(str).str.upper() == "ENABLED"] if st_col else df
    flagged = []
    for _, row in active.iterrows():
        if "SHOPPING" in to_str(row[ch_col]).upper():
            bst = to_str(row[bid_col]).upper()
            name = to_str(row[name_col]) if name_col else ""
            cid = to_str(row[cid_col]) if cid_col else ""
            spend = spend_map.get(cid, 0) or 0
            is_suppression = re.search(r'\b(suppression|zombie|suppress)\b', name, re.IGNORECASE)
            if "MANUAL_CPC" in bst and spend > 100 and not is_suppression:
                flagged.append(f"{name} (spend: {money_str(spend)})")

    if not flagged:
        return ControlResult(STATUS_OK, "No Shopping campaigns with >$100 spend using unjustified MANUAL_CPC.", WHY["F015"])
    return ControlResult(STATUS_FLAG, f"{len(flagged)} Shopping campaign(s) using MANUAL_CPC with spend > $100: {', '.join(flagged[:3])}.", WHY["F015"])


def _f016(ctx: GoogleContext) -> ControlResult:
    """Budget Concentration — PMAX Dominance"""
    df = get_sheet(ctx, "CHANNEL_TYPE")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 07 not found.", WHY["F016"])

    ch_col  = find_col(df, ["AdvertisingChannelType"])
    pct_col = find_col(df, ["Perc_Spend"])
    spd_col = find_col(df, ["Spend"])
    if not ch_col:
        return ControlResult(STATUS_FLAG, "AdvertisingChannelType not found in Tab 07.", WHY["F016"])

    total = sum(to_float(r[spd_col]) or 0 for _, r in df.iterrows()) if spd_col else 0
    channel_pcts = {}
    for _, row in df.iterrows():
        ch = to_str(row[ch_col]).upper()
        if pct_col:
            pct = to_float(row[pct_col]) or 0
        elif spd_col and total > 0:
            pct = (to_float(row[spd_col]) or 0) / total
        else:
            pct = 0
        channel_pcts[ch] = pct

    pmax   = channel_pcts.get("PERFORMANCE_MAX", 0)
    search = channel_pcts.get("SEARCH", 0)

    if pmax > 0.85 and search < 0.05:
        status = STATUS_FLAG
    elif pmax > 0.70 and search < 0.10:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    breakdown = ", ".join(f"{k}: {v*100:.1f}%" for k, v in channel_pcts.items())
    return ControlResult(status, f"PMAX spend share = {pmax*100:.1f}%. Search = {search*100:.1f}%. Channel breakdown: {breakdown}.", WHY["F016"])


def _f017(ctx: GoogleContext) -> ControlResult:
    """ACoS vs Constraint Alignment"""
    df02 = get_sheet(ctx, "DATE_RANGE_KPIS")
    df22 = get_sheet(ctx, "CLIENT_SUCCESS")
    if df02.empty or df22.empty:
        return ControlResult(STATUS_FLAG, "Tab 02 or 22 not found.", WHY["F017"])

    acos_col = find_col(df02, ["ACoS", "acos"])
    if not acos_col:
        return ControlResult(STATUS_FLAG, "ACoS column not found in Tab 02.", WHY["F017"])

    current_acos = to_float(df02.iloc[0][acos_col])
    constraint   = to_float(df22.iloc[0].iloc[14]) if len(df22.iloc[0]) > 14 else None

    if current_acos is None:
        return ControlResult(STATUS_FLAG, "ACoS value not found in Tab 02.", WHY["F017"])
    if constraint is None or constraint == 0:
        return ControlResult(STATUS_PARTIAL, f"Current ACoS = {pct_str(current_acos)}. No ACoS constraint found in Salesforce.", WHY["F017"])

    variance = (current_acos - constraint) / constraint
    if variance <= 0.10:
        status = STATUS_OK
    elif variance <= 0.20:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Current ACoS = {pct_str(current_acos)}. Declared constraint = {pct_str(constraint)}. Variance = {variance*100:+.1f}% vs constraint.",
        WHY["F017"],
    )


def _f018(ctx: GoogleContext) -> ControlResult:
    """Budget vs MRR Alignment"""
    df02 = get_sheet(ctx, "DATE_RANGE_KPIS")
    df22 = get_sheet(ctx, "CLIENT_SUCCESS")
    if df02.empty or df22.empty:
        return ControlResult(STATUS_FLAG, "Tab 02 or 22 not found.", WHY["F018"])

    spend_col = find_col(df02, ["AdSpend"])
    if not spend_col:
        return ControlResult(STATUS_FLAG, "AdSpend not found in Tab 02.", WHY["F018"])

    actual = to_float(df02.iloc[0][spend_col])
    budget = to_float(df22.iloc[0].iloc[35]) if len(df22.iloc[0]) > 35 else None

    if actual is None or budget is None or budget == 0:
        return ControlResult(STATUS_PARTIAL, f"Actual spend = {money_str(actual)}. Budget = {money_str(budget)}. Cannot compute variance.", WHY["F018"])

    window_days = ctx.window_days or 30
    prorated = budget * (window_days / 30.0)
    variance = (actual - prorated) / prorated

    if -0.10 <= variance <= 0.10:
        status = STATUS_OK
    elif -0.20 <= variance <= 0.15:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Actual spend = {money_str(actual)}. Prorated target = {money_str(prorated)}. Variance = {variance*100:+.1f}% vs target.",
        WHY["F018"],
    )


def _f019(ctx: GoogleContext) -> ControlResult:
    """Feed Product Availability"""
    df = get_sheet(ctx, "FEED_PRODUCTS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 30 not found.", WHY["F019"])

    avail_col = find_col(df, ["Availability"])
    cost_col  = find_col(df, ["cost"])
    if not avail_col:
        return ControlResult(STATUS_PARTIAL, "Availability column not found.", WHY["F019"])

    oos_mask = df[avail_col].astype(str).str.lower().str.contains("out of stock")
    oos_with_spend = df[oos_mask]
    if cost_col:
        oos_with_spend = oos_with_spend[oos_with_spend[cost_col].apply(to_float).fillna(0) > 0]

    oos_spend = oos_with_spend[cost_col].apply(to_float).fillna(0).sum() if cost_col else 0

    if len(oos_with_spend) == 0:
        return ControlResult(STATUS_OK, "No out-of-stock products with active spend found in feed.", WHY["F019"])
    return ControlResult(
        STATUS_FLAG,
        f"{len(oos_with_spend)} out-of-stock product(s) with spend > $0. Total spend on unavailable products: {money_str(oos_spend)}.",
        WHY["F019"],
    )


def _f020(ctx: GoogleContext) -> ControlResult:
    """Price Competitiveness"""
    df = get_sheet(ctx, "PRICE_COMPETITIVENESS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Price competitiveness data not available.", WHY["F020"])

    gap_col  = find_col(df, ["price_gap_perc"])
    cost_col = find_col(df, ["cost"])
    if not gap_col:
        return ControlResult(STATUS_PARTIAL, "price_gap_perc column not found.", WHY["F020"])

    with_spend = df if cost_col is None else df[df[cost_col].apply(to_float).fillna(0) > 0]
    total = len(with_spend)
    if total == 0:
        return ControlResult(STATUS_OK, "No products with spend found to evaluate price competitiveness.", WHY["F020"])

    below_30 = sum(1 for v in with_spend[gap_col].apply(to_float) if v is not None and v < -0.30)
    pct = below_30 / total

    if pct < 0.10:
        status = STATUS_OK
    elif pct < 0.20:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    avg_gap = with_spend[gap_col].apply(to_float).dropna().mean()
    return ControlResult(
        status,
        f"{below_30} of {total} products with spend have price_gap_perc < -30%. Average price gap: {avg_gap*100:.1f}%.",
        WHY["F020"],
    )


def _f021(ctx: GoogleContext) -> ControlResult:
    """PMAX Channel Distribution"""
    df = get_sheet(ctx, "PMAX_CHANNELS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 18 (PMAX Channels) not found.", WHY["F021"])

    ft_col   = find_col(df, ["FieldType"])
    cost_col = find_col(df, ["Cost", "cost"])
    if not ft_col or not cost_col:
        return ControlResult(STATUS_PARTIAL, "FieldType or Cost not found in Tab 18.", WHY["F021"])

    total = sum(to_float(r[cost_col]) or 0 for _, r in df.iterrows())
    if total == 0:
        return ControlResult(STATUS_FLAG, "Total PMAX spend is zero.", WHY["F021"])

    by_type = {}
    for _, row in df.iterrows():
        ft = to_str(row[ft_col]).upper()
        cost = to_float(row[cost_col]) or 0
        by_type[ft] = by_type.get(ft, 0) + cost

    shopping_pct = by_type.get("SHOPPING", 0) / total
    display_pct  = by_type.get("DISPLAY", 0) / total

    if shopping_pct >= 1.0 or display_pct == 0:
        status = STATUS_FLAG if shopping_pct > 0.90 else STATUS_PARTIAL
    else:
        status = STATUS_OK

    parts = ", ".join(f"{k}: {v/total*100:.1f}%" for k, v in sorted(by_type.items()))
    return ControlResult(status, f"PMAX distribution — {parts}. Total PMAX spend: {money_str(total)}.", WHY["F021"])


# Manual controls F022-F027, F030, F032, F034, F035

def _manual_ok(cid: str, msg: str, why: str) -> ControlResult:
    return ControlResult(STATUS_OK, msg, why)


def _f022(ctx): return _manual_ok("F022", "Manual review required. Check Google Ads Assets > Sitelinks. Minimum 4 required.", WHY["F022"])
def _f023(ctx): return _manual_ok("F023", "Manual review required. Check Google Ads Assets > Structured Snippets.", WHY["F023"])
def _f024(ctx): return _manual_ok("F024", "Manual review required. Check Google Ads Assets > Callouts.", WHY["F024"])
def _f025(ctx): return _manual_ok("F025", "Manual review required. Check Google Ads Assets > Business Name.", WHY["F025"])


def _f026(ctx: GoogleContext) -> ControlResult:
    """Logos Approved — uses Tab 33"""
    df = get_sheet(ctx, "ASSETS_EXTENSIONS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Assets tab (33) not found. Manual logo check required in Google Ads.", WHY["F026"])

    ft_col     = find_col(df, ["FieldType"])
    approval   = find_col(df, ["PolicyApprovalStatus"])
    status_col = find_col(df, ["Status"])
    if not ft_col:
        return ControlResult(STATUS_PARTIAL, "FieldType not found in Tab 33.", WHY["F026"])

    image_types = {"MARKETING_IMAGE", "SQUARE_MARKETING_IMAGE", "PORTRAIT_MARKETING_IMAGE"}
    approved_images = df[
        (df[ft_col].astype(str).str.upper().isin(image_types)) &
        (df[approval].astype(str).str.upper() == "APPROVED" if approval else pd.Series([True]*len(df))) &
        (df[status_col].astype(str).str.upper() == "ENABLED" if status_col else pd.Series([True]*len(df)))
    ]

    count = len(approved_images)
    if count >= 1:
        return ControlResult(STATUS_OK, f"{count} approved image asset(s) found in active PMAX asset groups.", WHY["F026"])
    return ControlResult(STATUS_FLAG, "No approved image assets found in active PMAX asset groups.", WHY["F026"])


def _f027(ctx: GoogleContext) -> ControlResult:
    """Ad Strength — proxy via PerformanceLabel from Tab 33"""
    df = get_sheet(ctx, "ASSETS_EXTENSIONS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Assets tab (33) not found. Manual ad strength check required.", WHY["F027"])

    perf_col   = find_col(df, ["PerformanceLabel"])
    status_col = find_col(df, ["Status"])
    if not perf_col:
        return ControlResult(STATUS_PARTIAL, "PerformanceLabel not found in Tab 33. Manual ad strength check required.", WHY["F027"])

    active = df[df[status_col].astype(str).str.upper() == "ENABLED"] if status_col else df
    counts = active[perf_col].astype(str).str.upper().value_counts().to_dict()

    excellent = counts.get("BEST", 0)
    good      = counts.get("GOOD", 0)
    low       = counts.get("LOW", 0)
    total     = sum(counts.values())

    if excellent > 0 or good > 0:
        status = STATUS_OK
    elif low > 0 and excellent == 0 and good == 0:
        status = STATUS_FLAG
    else:
        status = STATUS_PARTIAL

    parts = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()) if k not in ("NAN","UNKNOWN"))
    return ControlResult(
        status,
        f"Performance labels across active asset group assets — {parts}. Note: this is an asset-level proxy, not account-level ad strength.",
        WHY["F027"],
    )


def _f028(ctx: GoogleContext) -> ControlResult:
    """DPL Coverage"""
    df = get_sheet(ctx, "DPL_PERFORMANCE")
    if df.empty:
        return ControlResult(STATUS_FLAG, "DPL Performance tab (28) returned no data. DPL may not be configured for this account.", WHY["F028"])

    return ControlResult(STATUS_OK, f"DPL Performance data found. {len(df)} records in window.", WHY["F028"])


def _f029(ctx: GoogleContext) -> ControlResult:
    """Product Type Coverage in Feed"""
    df = get_sheet(ctx, "FEED_PRODUCTS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 30 not found.", WHY["F029"])

    pt_col = find_col(df, ["ProductType", "product_type"])
    if not pt_col:
        return ControlResult(STATUS_FLAG, "ProductType column not found.", WHY["F029"])

    total = len(df)
    missing = (df[pt_col].isna() | (df[pt_col].astype(str).str.strip() == "")).sum()
    pct_missing = missing / total if total > 0 else 0

    if pct_missing <= 0.15:
        status = STATUS_OK
    elif pct_missing <= 0.30:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"{missing} of {total} active products ({pct_missing*100:.1f}%) have null ProductType.",
        WHY["F029"],
    )


def _f030(ctx: GoogleContext) -> ControlResult:
    """PMAX Listing Group Eligible — uses Tab 32"""
    df = get_sheet(ctx, "ASSET_GROUPS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Asset Groups tab (32) not found. Manual listing group check required.", WHY["F030"])

    primary_col = find_col(df, ["PrimaryStatus"])
    ag_status   = find_col(df, ["AssetGroupStatus"])
    name_col    = find_col(df, ["AssetGroupName"])

    if not primary_col:
        return ControlResult(STATUS_PARTIAL, "PrimaryStatus not found in Tab 32.", WHY["F030"])

    active = df[df[ag_status].astype(str).str.upper() == "ENABLED"] if ag_status else df
    ineligible = active[~active[primary_col].astype(str).str.upper().isin(["ELIGIBLE"])]
    total_active = len(active)
    ineligible_count = len(ineligible)

    if ineligible_count == 0:
        return ControlResult(STATUS_OK, f"All {total_active} active PMAX asset groups are eligible.", WHY["F030"])
    elif ineligible_count < total_active:
        names = ", ".join(ineligible[name_col].astype(str).head(3).tolist()) if name_col else ""
        return ControlResult(STATUS_PARTIAL, f"{ineligible_count} of {total_active} active asset groups are not eligible. Examples: {names}.", WHY["F030"])
    else:
        return ControlResult(STATUS_FLAG, f"All {ineligible_count} active PMAX asset groups are not eligible.", WHY["F030"])


def _f031(ctx: GoogleContext) -> ControlResult:
    """Shopping Campaign Priority — infer from campaign name"""
    df = get_sheet(ctx, "CAMPAIGNS_V2_ENRICHED")
    if df.empty:
        df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Campaign data not found. Manual priority check required.", WHY["F031"])

    name_col = find_col(df, ["CampaignName"])
    ch_col   = find_col(df, ["AdvertisingChannelType", "CampaignType"])
    st_col   = find_col(df, ["Status", "State", "IsEnabled"])
    if not name_col or not ch_col:
        return ControlResult(STATUS_PARTIAL, "CampaignName or channel type not found.", WHY["F031"])

    shopping = [r for _, r in df.iterrows()
                if "SHOPPING" in to_str(r[ch_col]).upper()
                and (not st_col or to_str(r[st_col]).upper() not in ("PAUSED", "REMOVED", "FALSE", "0"))]

    if not shopping:
        return ControlResult(STATUS_OK, "No active Shopping campaigns found to evaluate priority.", WHY["F031"])

    conflicts = []
    for row in shopping:
        name = to_str(row[name_col])
        is_general  = bool(re.search(r'\b(general|catchall|catch.all|everything)\b', name, re.IGNORECASE))
        is_remnant  = bool(re.search(r'\b(remnant)\b', name, re.IGNORECASE))
        is_zombie   = bool(re.search(r'\b(zombie)\b', name, re.IGNORECASE))
        if not (is_general or is_remnant or is_zombie):
            continue
        if is_general and is_remnant:
            conflicts.append(f"{name} (both General and Remnant patterns)")

    if not conflicts:
        return ControlResult(
            STATUS_PARTIAL,
            f"{len(shopping)} active Shopping campaign(s). Priority inferred from naming — actual Priority field requires manual verification in Google Ads.",
            WHY["F031"],
        )
    return ControlResult(STATUS_FLAG, f"Priority conflicts detected: {', '.join(conflicts[:3])}.", WHY["F031"])


def _f032(ctx): return _manual_ok("F032", "Manual review required. Verify Keyword Expander status in QT Portal > Google Channel.", WHY["F032"])


def _f033(ctx: GoogleContext) -> ControlResult:
    """Full Funnel Channel Coverage"""
    df = get_sheet(ctx, "CHANNEL_TYPE")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 07 not found.", WHY["F033"])

    ch_col  = find_col(df, ["AdvertisingChannelType"])
    spd_col = find_col(df, ["Spend"])
    if not ch_col or not spd_col:
        return ControlResult(STATUS_FLAG, "Channel type or spend column not found.", WHY["F033"])

    active_channels = []
    for _, row in df.iterrows():
        ch = to_str(row[ch_col]).upper()
        sp = to_float(row[spd_col]) or 0
        if sp > 0:
            active_channels.append(ch)

    has_pmax   = any("PERFORMANCE_MAX" in c for c in active_channels)
    has_search = any("SEARCH" in c for c in active_channels)

    if has_pmax and has_search:
        return ControlResult(STATUS_OK, f"Active channels with spend: {', '.join(active_channels)}.", WHY["F033"])
    elif has_pmax or has_search:
        return ControlResult(STATUS_PARTIAL, f"Only one primary channel active with spend: {', '.join(active_channels)}. Full funnel coverage requires both PMAX and Search.", WHY["F033"])
    else:
        return ControlResult(STATUS_FLAG, f"Active channels: {', '.join(active_channels) or 'none'}. No PMAX or Search spend detected.", WHY["F033"])


def _f034(ctx): return _manual_ok("F034", "Manual review required. Verify PMAX audience configuration in Google Ads Asset Groups > Audiences.", WHY["F034"])
def _f035(ctx): return _manual_ok("F035", "Manual review required. Verify PMAX Search Themes count in Google Ads Asset Groups.", WHY["F035"])


def _f036(ctx: GoogleContext) -> ControlResult:
    """Device Performance Imbalance"""
    df = get_sheet(ctx, "DEVICE_BREAKDOWN")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 16 not found.", WHY["F036"])

    dev_col  = find_col(df, ["Device"])
    spd_col  = find_col(df, ["Spend"])
    ord_col  = find_col(df, ["Orders", "Conversions"])
    clk_col  = find_col(df, ["Clicks"])
    if not dev_col or not spd_col:
        return ControlResult(STATUS_PARTIAL, "Device or Spend column not found.", WHY["F036"])

    data = {}
    for _, row in df.iterrows():
        dev = to_str(row[dev_col]).upper()
        spd = to_float(row[spd_col]) or 0
        clk = to_float(row[clk_col]) if clk_col else 0
        orders = to_float(row[ord_col]) if ord_col else 0
        cr = (orders / clk) if clk and clk > 0 else 0
        data[dev] = {"spend": spd, "cr": cr}

    total = sum(v["spend"] for v in data.values()) or 1
    mobile  = data.get("MOBILE", {})
    desktop = data.get("DESKTOP", {})

    mobile_pct = mobile.get("spend", 0) / total
    mobile_cr  = mobile.get("cr", 0)
    desktop_cr = desktop.get("cr", 0)

    if mobile_pct > 0.40 and desktop_cr > 0 and mobile_cr < desktop_cr * 0.50:
        status = STATUS_FLAG
    elif mobile_pct > 0.30 and desktop_cr > 0 and mobile_cr < desktop_cr * 0.70:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    return ControlResult(
        status,
        f"Mobile spend share = {mobile_pct*100:.1f}%. Mobile CR = {mobile_cr*100:.2f}%. Desktop CR = {desktop_cr*100:.2f}%. Mobile CR as % of Desktop CR = {(mobile_cr/desktop_cr*100 if desktop_cr > 0 else 0):.1f}%.",
        WHY["F036"],
    )


def _f037(ctx: GoogleContext) -> ControlResult:
    """Geo Spend Concentration"""
    df = get_sheet(ctx, "LOCATION_PERF")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Location Performance tab (26) not found.", WHY["F037"])

    region_col = find_col(df, ["State", "Region", "region"])
    cost_col   = find_col(df, ["Cost", "cost"])
    conv_col   = find_col(df, ["Conversions", "conversions"])
    if not region_col or not cost_col:
        return ControlResult(STATUS_PARTIAL, "Region or Cost not found in Tab 26.", WHY["F037"])

    grouped = df.groupby(region_col).agg(
        total_cost=(cost_col, "sum"),
        total_conv=(conv_col, "sum") if conv_col else (cost_col, "count")
    ).reset_index().sort_values("total_cost", ascending=False)

    total_spend = grouped["total_cost"].sum()
    total_conv  = grouped["total_conv"].sum()

    top3_spend = grouped.head(3)["total_cost"].sum()
    top3_conv  = grouped.head(3)["total_conv"].sum()

    pct_spend = top3_spend / total_spend if total_spend > 0 else 0
    pct_conv  = top3_conv / total_conv if total_conv > 0 else 0

    zero_conv_states = len(grouped[(grouped["total_cost"] > 0) & (grouped["total_conv"] == 0)])
    top3_names = ", ".join(grouped.head(3)[region_col].astype(str).tolist())

    if pct_spend > 0.90 and pct_conv < 0.50:
        status = STATUS_FLAG
    elif pct_spend > 0.70 and pct_conv < 0.60:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    return ControlResult(
        status,
        f"Top 3 states ({top3_names}) = {pct_spend*100:.1f}% of spend, {pct_conv*100:.1f}% of conversions. {zero_conv_states} state(s) with spend and zero conversions.",
        WHY["F037"],
    )


def _f038(ctx: GoogleContext) -> ControlResult:
    """MultiChannel Product Coverage"""
    df19 = get_sheet(ctx, "MULTICHANNEL_PRODUCTS")
    df27 = get_sheet(ctx, "AMAZON_PRODUCT")

    mc_count = len(df19) if not df19.empty else 0
    amz_count = len(df27) if not df27.empty else 0

    if mc_count == 0 and amz_count == 0:
        return ControlResult(STATUS_PARTIAL, "No multi-channel product data found. Account may be Google-only.", WHY["F038"])
    return ControlResult(STATUS_OK, f"MultiChannel Products: {mc_count} records. Amazon Product tab: {amz_count} records.", WHY["F038"])


def _f039(ctx: GoogleContext) -> ControlResult:
    """Conversion Tracking Active"""
    df = get_sheet(ctx, "CAMPAIGN_GOLD")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 13 not found.", WHY["F039"])

    cid_col  = find_col(df, ["CampaignId"])
    name_col = find_col(df, ["CampaignName"])
    cost_col = find_col(df, ["Cost", "cost"])
    conv_col = find_col(df, ["Conversions", "conversions"])
    if not cid_col or not cost_col:
        return ControlResult(STATUS_FLAG, "CampaignId or Cost not found in Tab 13.", WHY["F039"])

    agg = df.groupby(cid_col).agg(
        total_cost=(cost_col, "sum"),
        total_conv=(conv_col, "sum") if conv_col else (cost_col, "count"),
        name=(name_col, "first") if name_col else (cost_col, "count")
    ).reset_index()

    flagged = agg[(agg["total_cost"] > 50) & (agg["total_conv"] == 0)]
    zero_conv_spend = flagged["total_cost"].sum()
    names = ", ".join(flagged["name"].astype(str).head(3).tolist()) if name_col else ""

    if len(flagged) == 0:
        return ControlResult(STATUS_OK, "All campaigns with spend > $50 have conversion data.", WHY["F039"])
    return ControlResult(
        STATUS_FLAG,
        f"{len(flagged)} campaign(s) with spend > $50 and zero conversions. Total spend: {money_str(zero_conv_spend)}. Examples: {names}.",
        WHY["F039"],
    )


def _f040(ctx: GoogleContext) -> ControlResult:
    """YoY ACoS Trend"""
    df = get_sheet(ctx, "YEARLY_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 03 not found.", WHY["F040"])

    from rules_engine_google_health import _yoy_float, _yoy_this, _yoy_prev
    yoy  = _yoy_float(df, "ACoS")
    curr = _yoy_this(df, "ACoS")
    prev = _yoy_prev(df, "ACoS")

    if yoy is None:
        return ControlResult(STATUS_FLAG, "ACoS row not found in Tab 03.", WHY["F040"])

    if yoy <= 0.05:   status = STATUS_OK
    elif yoy <= 0.15: status = STATUS_PARTIAL
    else:             status = STATUS_FLAG

    c = pct_str(curr) if curr else "N/A"
    p = pct_str(prev) if prev else "N/A"
    return ControlResult(status, f"Current ACoS = {c}. Prior year ACoS = {p}. YoY change = {yoy*100:+.1f}%.", WHY["F040"])


def _f041(ctx: GoogleContext) -> ControlResult:
    """PoP Spend Variance"""
    df = get_sheet(ctx, "DATE_RANGE_KPIS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 02 not found.", WHY["F041"])

    spend_col = find_col(df, ["AdSpend"])
    prev_col  = find_col(df, ["Prev_AdSpend"])
    if not spend_col or not prev_col:
        return ControlResult(STATUS_PARTIAL, "AdSpend or Prev_AdSpend not found.", WHY["F041"])

    curr = to_float(df.iloc[0][spend_col])
    prev = to_float(df.iloc[0][prev_col])

    if curr is None or prev is None or prev == 0:
        return ControlResult(STATUS_PARTIAL, f"Current spend = {money_str(curr)}. Prior period spend not available.", WHY["F041"])

    variance = (curr - prev) / prev
    if abs(variance) <= 0.15:
        status = STATUS_OK
    elif abs(variance) <= 0.30:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(
        status,
        f"Spend variance vs prior period = {variance*100:+.1f}%. Current: {money_str(curr)}. Prior: {money_str(prev)}.",
        WHY["F041"],
    )


def _f042(ctx): return ControlResult(STATUS_OK, "Manual review required during QR presentation call. Interaction and explanation quality cannot be assessed from system data.", WHY["F042"])


# ── Orchestrator ──────────────────────────────────────────────────────────────

_EVALUATORS = {
    "F001": _f001, "F002": _f002, "F003": _f003, "F004": _f004, "F005": _f005,
    "F006": _f006, "F007": _f007, "F008": _f008, "F009": _f009, "F010": _f010,
    "F011": _f011, "F012": _f012, "F013": _f013, "F014": _f014, "F015": _f015,
    "F016": _f016, "F017": _f017, "F018": _f018, "F019": _f019, "F020": _f020,
    "F021": _f021, "F022": _f022, "F023": _f023, "F024": _f024, "F025": _f025,
    "F026": _f026, "F027": _f027, "F028": _f028, "F029": _f029, "F030": _f030,
    "F031": _f031, "F032": _f032, "F033": _f033, "F034": _f034, "F035": _f035,
    "F036": _f036, "F037": _f037, "F038": _f038, "F039": _f039, "F040": _f040,
    "F041": _f041, "F042": _f042,
}


def evaluate_all_framework(ctx: GoogleContext) -> Dict[str, ControlResult]:
    results = {}
    for cid, fn in _EVALUATORS.items():
        try:
            results[cid] = fn(ctx)
        except Exception as e:
            results[cid] = ControlResult(STATUS_FLAG, f"Evaluation error: {e}", "Internal error — review manually.")
    return results
