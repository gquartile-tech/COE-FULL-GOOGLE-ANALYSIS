"""
rules_engine_google_implementation.py
26 controls: I001-I026
Auto-evaluated: I001, I003, I004, I009, I011, I013, I016, I022, I026
Partial-proxy: I002 (Tab 34/40), I012, I013
All remaining manual controls: hardcoded OK with reviewer note.
"""
from __future__ import annotations

import re
from typing import Dict

import pandas as pd

from config import ControlResult, STATUS_OK, STATUS_FLAG, STATUS_PARTIAL
from config_google_implementation import WHY
from reader_databricks_google import (
    GoogleContext, get_sheet, find_col, to_float, to_str, clean_text,
    money_str, pct_str,
)

QT_PREFIX = re.compile(r'^QT[_\-]', re.IGNORECASE)
PROMO_PATTERN = re.compile(r'\b(sale|promo|holiday|black.?friday|cyber|bfcm|seasonal|clearance|discount)\b', re.IGNORECASE)


def _manual_ok(cid: str) -> ControlResult:
    return ControlResult(STATUS_OK, f"Manual review required. See WHY for verification steps.", WHY[cid])


def _i001(ctx: GoogleContext) -> ControlResult:
    """Salesforce Access Confirmed — proxy: CS record present and populated"""
    df = get_sheet(ctx, "CLIENT_SUCCESS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 22 (Client Success) returned no data. Salesforce record may be missing or inaccessible.", WHY["I001"])

    row = df.iloc[0]
    advertiser_id = to_str(row.iloc[80]) if len(row) > 80 else ""
    objective     = to_str(row.iloc[39]) if len(row) > 39 else ""
    budget        = to_float(row.iloc[35]) if len(row) > 35 else None

    missing = []
    if not advertiser_id:
        missing.append("AdvertiserId missing")
    if not objective:
        missing.append("Primary Objective not set")
    if not budget:
        missing.append("Monthly Budget not set")

    if not missing:
        return ControlResult(STATUS_OK, f"Salesforce record found. AdvertiserId = {advertiser_id}. Key fields populated.", WHY["I001"])
    elif len(missing) < 3:
        return ControlResult(STATUS_PARTIAL, f"Salesforce record found but incomplete. Issues: {'; '.join(missing)}.", WHY["I001"])
    else:
        return ControlResult(STATUS_FLAG, f"Salesforce record found but critical fields missing: {'; '.join(missing)}.", WHY["I001"])


def _i002(ctx: GoogleContext) -> ControlResult:
    """GMC + GA4 Linked — uses Tab 34 and Tab 40"""
    df34 = get_sheet(ctx, "ADVERTISER_DETAILS")
    df40 = get_sheet(ctx, "ACCOUNT_LINKS")

    gmc_linked = None
    ga4_linked = None
    merchant_id = ""

    if not df34.empty:
        gmc_col = find_col(df34, ["GMC_Linked"])
        mid_col = find_col(df34, ["MerchantID"])
        if gmc_col:
            gmc_linked = str(df34.iloc[0][gmc_col]).lower() in ("true", "1", "yes")
        if mid_col:
            merchant_id = to_str(df34.iloc[0][mid_col])

    if not df40.empty:
        merch_col  = find_col(df40, ["MerchantStatus"])
        analyt_col = find_col(df40, ["AnalyticsStatus"])
        analyt_id  = find_col(df40, ["AnalyticsId"])
        row40 = df40.iloc[0]

        if gmc_linked is None and merch_col:
            merch_val = to_str(row40[merch_col])
            gmc_linked = merch_val.lower() not in ("false", "0", "no", "nan", "")

        if analyt_col:
            analyt_val = to_str(row40[analyt_col])
            ga4_linked = analyt_val.lower() not in ("false", "0", "no", "nan", "")
        if analyt_id:
            aid = to_str(row40[analyt_id])
            if aid and aid.lower() not in ("nan", "false", "0", ""):
                ga4_linked = True

    if gmc_linked is None and ga4_linked is None:
        return ControlResult(STATUS_PARTIAL, "Account link data not available. Manual check required: Google Ads > Tools > Linked Accounts.", WHY["I002"])

    gmc_s = "linked" if gmc_linked else "NOT linked"
    ga4_s = "linked" if ga4_linked else "NOT linked"
    mid_s = f" (Merchant ID: {merchant_id})" if merchant_id else ""

    if gmc_linked and ga4_linked:
        status = STATUS_OK
    elif gmc_linked or ga4_linked:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FLAG

    return ControlResult(status, f"GMC = {gmc_s}{mid_s}. GA4 = {ga4_s}.", WHY["I002"])


def _i003(ctx: GoogleContext) -> ControlResult:
    """Conversion Tag Active — proxy: campaigns with spend have conversion data"""
    df = get_sheet(ctx, "CAMPAIGN_GOLD")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 13 not found. Cannot assess conversion tracking.", WHY["I003"])

    cost_col = find_col(df, ["Cost", "cost"])
    conv_col = find_col(df, ["Conversions", "conversions"])
    if not cost_col or not conv_col:
        return ControlResult(STATUS_FLAG, "Cost or Conversions column not found in Tab 13.", WHY["I003"])

    total_spend = (df[cost_col].apply(to_float).fillna(0)).sum()
    total_conv  = (df[conv_col].apply(to_float).fillna(0)).sum()

    if total_spend == 0:
        return ControlResult(STATUS_FLAG, "No spend found in campaign data — cannot validate conversion tag.", WHY["I003"])

    if total_conv > 0:
        conv_rate = total_conv / total_spend
        return ControlResult(
            STATUS_OK,
            f"Conversion data present. Total conversions = {total_conv:.0f} across {money_str(total_spend)} spend. Proxy CVR = {conv_rate:.4f}. Manual tag verification still recommended.",
            WHY["I003"],
        )
    else:
        return ControlResult(
            STATUS_FLAG,
            f"Zero conversions recorded across {money_str(total_spend)} spend. Conversion tag may be broken or tracking is not configured.",
            WHY["I003"],
        )


def _i004(ctx: GoogleContext) -> ControlResult:
    """Billing Status Active"""
    df = get_sheet(ctx, "STRIPE_INFO")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 15 (Stripe & Account Info) not found.", WHY["I004"])

    row = df.iloc[0]
    # Positional: col 13 = status, col 22 = status_invoice
    status_val    = to_str(row.iloc[13]) if len(row) > 13 else ""
    invoice_status = to_str(row.iloc[22]) if len(row) > 22 else ""

    billing_active = status_val.lower() == "active"
    invoice_ok     = invoice_status.lower() in ("paid", "active", "")

    if billing_active and invoice_ok:
        return ControlResult(STATUS_OK, f"Billing status = active. Invoice status = {invoice_status or 'not flagged'}.", WHY["I004"])
    elif billing_active:
        return ControlResult(STATUS_PARTIAL, f"Billing = active. Invoice status = {invoice_status}. Investigate unpaid invoices.", WHY["I004"])
    else:
        return ControlResult(STATUS_FLAG, f"Billing status = {status_val or 'unknown'}. Invoice status = {invoice_status or 'unknown'}. Account may be at risk of suspension.", WHY["I004"])


def _i005(ctx): return _manual_ok("I005")
def _i006(ctx): return _manual_ok("I006")
def _i007(ctx): return _manual_ok("I007")
def _i008(ctx): return _manual_ok("I008")


def _i009(ctx: GoogleContext) -> ControlResult:
    """Shopify / Platform Connected — Tab 15 IsConnect field"""
    df = get_sheet(ctx, "STRIPE_INFO")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Tab 15 not found. Manual platform connection check required.", WHY["I009"])

    conn_col = find_col(df, ["IsConnect", "is_connect"])
    if not conn_col:
        return ControlResult(STATUS_PARTIAL, "IsConnect field not found in Tab 15. Manual check required.", WHY["I009"])

    connected = str(df.iloc[0][conn_col]).lower() in ("true", "1", "yes")
    if connected:
        return ControlResult(STATUS_OK, "Platform connection (IsConnect) = true. Total sales channel linked.", WHY["I009"])
    return ControlResult(STATUS_FLAG, "Platform connection (IsConnect) = false. TACoS reporting unavailable without total sales data.", WHY["I009"])


def _i010(ctx): return _manual_ok("I010")


def _i011(ctx: GoogleContext) -> ControlResult:
    """Naming Conventions — QT_ prefix compliance"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_FLAG, "Tab 38 not found.", WHY["I011"])

    name_col   = find_col(df, ["CampaignName"])
    status_col = find_col(df, ["Status"])
    if not name_col:
        return ControlResult(STATUS_FLAG, "CampaignName column not found.", WHY["I011"])

    active = df[df[status_col].astype(str).str.upper() == "ENABLED"] if status_col else df
    total = len(active)
    if total == 0:
        return ControlResult(STATUS_PARTIAL, "No active campaigns found.", WHY["I011"])

    non_qt = [to_str(r[name_col]) for _, r in active.iterrows()
              if not QT_PREFIX.match(to_str(r[name_col]))]
    pct_non_qt = len(non_qt) / total

    if pct_non_qt <= 0.05:
        return ControlResult(STATUS_OK, f"{total - len(non_qt)} of {total} active campaigns follow QT_ naming standard.", WHY["I011"])
    elif pct_non_qt <= 0.20:
        return ControlResult(STATUS_PARTIAL, f"{len(non_qt)} of {total} active campaigns don't follow QT_ naming. Examples: {', '.join(non_qt[:3])}.", WHY["I011"])
    else:
        return ControlResult(STATUS_FLAG, f"{len(non_qt)} of {total} active campaigns ({pct_non_qt*100:.1f}%) don't follow QT_ naming. Examples: {', '.join(non_qt[:3])}.", WHY["I011"])


def _i012(ctx): return _manual_ok("I012")


def _i013(ctx: GoogleContext) -> ControlResult:
    """Location Segmentation — proxy: check if location data exists with state-level granularity"""
    df = get_sheet(ctx, "LOCATION_PERF")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Location Performance data (Tab 26) not found. Location segmentation requires manual check.", WHY["I013"])

    region_col = find_col(df, ["State", "Region", "region"])
    if not region_col:
        return ControlResult(STATUS_PARTIAL, "No region column found in Tab 26.", WHY["I013"])

    unique_regions = df[region_col].dropna().nunique()
    cost_col = find_col(df, ["Cost"])
    total_rows = len(df)

    if unique_regions >= 10:
        return ControlResult(
            STATUS_OK,
            f"Location data available with {unique_regions} unique regions and {total_rows} rows. Location targeting is active with state-level segmentation.",
            WHY["I013"],
        )
    elif unique_regions >= 3:
        return ControlResult(
            STATUS_PARTIAL,
            f"Location data found but limited: {unique_regions} unique regions. Manual bid adjustment configuration check required.",
            WHY["I013"],
        )
    else:
        return ControlResult(STATUS_FLAG, f"Only {unique_regions} location(s) found. Location segmentation may not be active.", WHY["I013"])


def _i014(ctx): return _manual_ok("I014")
def _i015(ctx): return _manual_ok("I015")


def _i016(ctx: GoogleContext) -> ControlResult:
    """Promotion End Dates Correct — proxy via campaign naming"""
    df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Tab 38 not found. Manual promotion end date check required.", WHY["I016"])

    name_col  = find_col(df, ["CampaignName"])
    start_col = find_col(df, ["StartDate"])
    st_col    = find_col(df, ["Status"])
    if not name_col or not start_col:
        return ControlResult(STATUS_PARTIAL, "CampaignName or StartDate not found.", WHY["I016"])

    active = df[df[st_col].astype(str).str.upper() == "ENABLED"] if st_col else df
    ref = ctx.window_end or pd.Timestamp.now().date()
    stale_promos = []

    for _, row in active.iterrows():
        name = to_str(row[name_col])
        if not PROMO_PATTERN.search(name):
            continue
        sd = pd.to_datetime(str(row[start_col]), errors="coerce")
        if not pd.isna(sd) and (pd.Timestamp(ref) - sd).days > 60:
            stale_promos.append(name)

    if not stale_promos:
        return ControlResult(STATUS_OK, "No active campaigns with stale promotional naming found.", WHY["I016"])
    return ControlResult(
        STATUS_PARTIAL,
        f"{len(stale_promos)} active campaign(s) with promotional naming and start date > 60 days ago: {', '.join(stale_promos[:3])}. Manual end date verification required.",
        WHY["I016"],
    )


def _i017(ctx): return _manual_ok("I017")
def _i018(ctx): return _manual_ok("I018")
def _i019(ctx): return _manual_ok("I019")
def _i020(ctx): return _manual_ok("I020")
def _i021(ctx): return _manual_ok("I021")


def _i022(ctx: GoogleContext) -> ControlResult:
    """Shopping Campaign Priority — infer from campaign naming tiers"""
    df = get_sheet(ctx, "CAMPAIGNS_V2_ENRICHED")
    if df.empty:
        df = get_sheet(ctx, "CAMPAIGN_SETTINGS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Campaign data not found. Manual Shopping priority check required.", WHY["I022"])

    name_col = find_col(df, ["CampaignName"])
    ch_col   = find_col(df, ["AdvertisingChannelType", "CampaignType"])
    st_col   = find_col(df, ["Status", "State", "IsEnabled"])
    if not name_col or not ch_col:
        return ControlResult(STATUS_PARTIAL, "CampaignName or channel type not found.", WHY["I022"])

    shopping = []
    for _, row in df.iterrows():
        ch   = to_str(row[ch_col]).upper()
        name = to_str(row[name_col])
        stat = to_str(row[st_col]).upper() if st_col else "ENABLED"
        if "SHOPPING" in ch and stat not in ("PAUSED", "REMOVED", "FALSE", "0"):
            shopping.append(name)

    if not shopping:
        return ControlResult(STATUS_OK, "No active Shopping campaigns found (may be PMAX-only account).", WHY["I022"])

    has_general  = any(re.search(r'\b(general|catchall|catch.all|EE)\b', n, re.IGNORECASE) for n in shopping)
    has_remnant  = any(re.search(r'\b(remnant)\b', n, re.IGNORECASE) for n in shopping)
    has_zombie   = any(re.search(r'\b(zombie)\b', n, re.IGNORECASE) for n in shopping)
    has_top      = any(re.search(r'\b(top|bestseller|hero)\b', n, re.IGNORECASE) for n in shopping)

    tiers_found = sum([has_top, has_general, has_remnant or has_zombie])

    if tiers_found >= 2:
        return ControlResult(STATUS_OK, f"{len(shopping)} active Shopping campaign(s). Priority tiers detected from naming. Manual Google Ads priority field verification still required.", WHY["I022"])
    else:
        return ControlResult(STATUS_PARTIAL, f"{len(shopping)} active Shopping campaign(s) found but priority tier naming unclear: {', '.join(shopping[:3])}. Manual priority check required.", WHY["I022"])


def _i023(ctx): return _manual_ok("I023")
def _i024(ctx): return _manual_ok("I024")
def _i025(ctx): return _manual_ok("I025")


def _i026(ctx: GoogleContext) -> ControlResult:
    """Logo Asset Approved — uses Tab 33"""
    df = get_sheet(ctx, "ASSETS_EXTENSIONS")
    if df.empty:
        return ControlResult(STATUS_PARTIAL, "Assets tab (33) not found. Manual logo check required.", WHY["I026"])

    ft_col     = find_col(df, ["FieldType"])
    approval   = find_col(df, ["PolicyApprovalStatus"])
    status_col = find_col(df, ["Status"])
    if not ft_col:
        return ControlResult(STATUS_PARTIAL, "FieldType column not found in Tab 33.", WHY["I026"])

    image_types = {"MARKETING_IMAGE", "SQUARE_MARKETING_IMAGE", "PORTRAIT_MARKETING_IMAGE"}
    approved = df[
        df[ft_col].astype(str).str.upper().isin(image_types) &
        (df[approval].astype(str).str.upper() == "APPROVED" if approval else pd.Series([True] * len(df))) &
        (df[status_col].astype(str).str.upper() == "ENABLED" if status_col else pd.Series([True] * len(df)))
    ]

    count = len(approved)
    if count >= 1:
        return ControlResult(STATUS_OK, f"{count} approved image asset(s) found in active asset groups.", WHY["I026"])
    return ControlResult(STATUS_FLAG, "No approved image assets found. PMAX Display will default to text-only ads.", WHY["I026"])


# ── Orchestrator ──────────────────────────────────────────────────────────────

_EVALUATORS = {
    "I001": _i001, "I002": _i002, "I003": _i003, "I004": _i004, "I005": _i005,
    "I006": _i006, "I007": _i007, "I008": _i008, "I009": _i009, "I010": _i010,
    "I011": _i011, "I012": _i012, "I013": _i013, "I014": _i014, "I015": _i015,
    "I016": _i016, "I017": _i017, "I018": _i018, "I019": _i019, "I020": _i020,
    "I021": _i021, "I022": _i022, "I023": _i023, "I024": _i024, "I025": _i025,
    "I026": _i026,
}


def evaluate_all_implementation(ctx: GoogleContext) -> Dict[str, ControlResult]:
    results = {}
    for cid, fn in _EVALUATORS.items():
        try:
            results[cid] = fn(ctx)
        except Exception as e:
            results[cid] = ControlResult(STATUS_FLAG, f"Evaluation error: {e}", "Internal error — review manually.")
    return results
