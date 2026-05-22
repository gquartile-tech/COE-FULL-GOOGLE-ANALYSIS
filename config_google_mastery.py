"""
config_google_mastery.py
14 controls: M001-M014
"""
from __future__ import annotations
from config import STATUS_OK, STATUS_FLAG, STATUS_PARTIAL, ControlResult

PILLAR = "google_mastery"
SCORING_EXCLUDED = {"M002"}  # touchpoint frequency is partial-manual
MAX_FINDINGS = 20

PRIORITY_POINTS = {10: -18, 9: -15, 8: -13, 7: -11, 6: -9, 5: -7, 4: -5, 3: -3, 2: -2, 1: 0}
IMPACT_LABEL    = {10: "Critical", 9: "High", 8: "High", 7: "Medium", 6: "Medium",
                   5: "Medium",   4: "Low",  3: "Low",  2: "Visibility", 1: "Visibility"}

IMPORTANCE = {
    "M001": 8, "M002": 5, "M003": 9, "M004": 9,
    "M005": 8, "M006": 7, "M007": 6, "M008": 7,
    "M009": 8, "M010": 7, "M011": 6, "M012": 8,
    "M013": 6, "M014": 9,
}

CONTROL_NAMES = {
    "M001": "Meeting Frequency",
    "M002": "Touchpoint Frequency",
    "M003": "Budgets & Goals Updated in Salesforce",
    "M004": "Salesforce Profile ID Populated",
    "M005": "Dynamic Performance Labels (DPL) Active",
    "M006": "Custom Labels (min 2 managed by QT)",
    "M007": "Feed Transformers / Mapping Active",
    "M008": "Price Competitiveness Active",
    "M009": "Feed-Based Inventory Filters",
    "M010": "Product Types Configured",
    "M011": "Brand Mapping Configured",
    "M012": "Quartile Portal Connection",
    "M013": "Account Segment Classification",
    "M014": "Primary Objective Documented",
}

WHY = {
    "M001": "Meeting cadence is the primary signal of client engagement health. Gaps increase churn risk.",
    "M002": "Biweekly touchpoints ensure clients stay informed. A long gap means the documented goals may be stale.",
    "M003": "Without documented targets, the agent cannot evaluate performance vs goal across any pillar.",
    "M004": "Profile ID links the Salesforce record to the Quartile Portal and reporting pipeline. Missing ID breaks data flow.",
    "M005": "DPLs are the foundational automation layer. Without them, bid adjustments and performance segmentation are manual.",
    "M006": "Custom labels enable product segmentation for bidding strategy. Fewer than 2 limits strategy depth.",
    "M007": "Feed transformers improve product title relevance, which directly impacts Shopping impression share and CTR.",
    "M008": "Without benchmark data, the account cannot identify pricing-driven impression loss.",
    "M009": "Serving ads to unavailable products wastes budget and degrades conversion rates and Quality Scores.",
    "M010": "Product types enable Shopping campaign structure by category. Missing types prevent proper CWCD targeting.",
    "M011": "Brand field enables separation of branded vs non-branded campaigns. Missing brands prevent TM campaign structure.",
    "M012": "Platform connection enables total sales visibility required to calculate TACoS and full funnel reporting.",
    "M013": "Incorrect segment classification leads to wrong benchmarks, incorrect pricing, and misaligned strategy.",
    "M014": "Undocumented objectives mean strategy recommendations lack a north star. All pillar evaluations depend on the primary goal.",
}

SOURCES = {
    "M001": "22_Client_Success[CreatedDate] — most recent QR record date",
    "M002": "22_Client_Success[SystemModstamp] — last CS update timestamp",
    "M003": "22_Client_Success[Monthly_Budget__c col 35, Primary_Spend_KPI__c col 74]",
    "M004": "22_Client_Success[AdvertiserId col 80] + 01_Advertiser_Name",
    "M005": "28_DPL_Performance — check if empty",
    "M006": "30_Feed_Products[CustomLabel0–CustomLabel4]",
    "M007": "30_Feed_Products[Title] — review for QT optimization patterns",
    "M008": "20_Price_Competitiveness[benchmark_price]",
    "M009": "30_Feed_Products[Availability, cost, conversions]",
    "M010": "30_Feed_Products[ProductType]",
    "M011": "30_Feed_Products[Brand]",
    "M012": "15_Stripe_and_Account_Info[IsConnect col 8] + 22_Client_Success[Channel__c col 79]",
    "M013": "15_Stripe_and_Account_Info[CustomerSegment col 9] + 22_Client_Success[Commodity_Products col 24]",
    "M014": "22_Client_Success[Primary_Objective__c col 39, Primary_Objective_Additional_Context__c col 38]",
}
