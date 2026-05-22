"""
config_google_strategy.py
21 controls: S001-S021
Strategy is reviewer-driven — no automated scoring thresholds.
All controls return flag/ok/partial based on data presence only.
S021 is manual.
"""
from __future__ import annotations
from config import STATUS_OK, STATUS_FLAG, STATUS_PARTIAL, ControlResult

PILLAR = "google_strategy"
SCORING_EXCLUDED = {f"S{str(i).zfill(3)}" for i in range(1, 22)}  # all excluded from scoring
MAX_FINDINGS = 25

PRIORITY_POINTS = {10: -18, 9: -15, 8: -13, 7: -11, 6: -9, 5: -7, 4: -5, 3: -3, 2: -2, 1: 0}
IMPACT_LABEL    = {10: "Critical", 9: "High", 8: "High", 7: "Medium", 6: "Medium",
                   5: "Medium",   4: "Low",  3: "Low",  2: "Visibility", 1: "Visibility"}

IMPORTANCE = {f"S{str(i).zfill(3)}": 6 for i in range(1, 22)}

CONTROL_NAMES = {
    "S001": "Catchall / Everything Else Campaign",
    "S002": "Top Products Campaign",
    "S003": "Price Tier / Margin Campaign",
    "S004": "Brand Campaign (Shopping/PMAX)",
    "S005": "Shopping Suppression Campaign Active",
    "S006": "Product Type Campaigns",
    "S007": "Zombie Campaign Active",
    "S008": "Remnant Campaign Active",
    "S009": "Query-Based Campaign Active",
    "S010": "Branded Search Campaign (TM Exact/SKW)",
    "S011": "Non-Brand (NB) Search Campaign",
    "S012": "DSA / NB DSA Campaign",
    "S013": "Match Type Strategy (Exact / Broad)",
    "S014": "Device Bid Adjustments Applied",
    "S015": "Demographic Segmentation (Age / Gender)",
    "S016": "Location Bid Adjustments Applied",
    "S017": "Campaign Budget Allocation Optimized",
    "S018": "PMAX vs Search vs Shopping Spend Balance",
    "S019": "Demand Gen Prospecting Campaign",
    "S020": "Demand Gen Remarketing Campaign",
    "S021": "Optimized Targeting Disabled (Display/DG)",
}

WHY = {
    "S001": "Without a Catchall, products not in dedicated campaigns receive no spend — revenue left on the table.",
    "S002": "Top Products campaigns concentrate budget on proven revenue drivers, improving account-level ROAS.",
    "S003": "Margin-based campaigns prevent low-margin products from consuming budget meant for profitable SKUs.",
    "S004": "Branded campaigns protect the brand SERP and capture high-CVR branded searches at low CPC.",
    "S005": "Suppression campaigns route unprofitable products into a controlled spend environment.",
    "S006": "Product-type segmentation enables category-level bid adjustments based on actual ROAS by category.",
    "S007": "Zombie campaigns give low-activity products controlled spend exposure, enabling recovery of dormant revenue.",
    "S008": "Remnant campaigns ensure full product catalog coverage at controlled low-priority spend.",
    "S009": "Query-based campaigns capture known high-converting search patterns at elevated bids.",
    "S010": "Branded Search campaigns capture high-intent branded queries at low CPC, protecting brand SERP.",
    "S011": "NB Search campaigns capture upper-funnel purchase intent that PMAX may not serve efficiently.",
    "S012": "DSA campaigns auto-generate ads from website content, capturing long-tail queries not in manual keywords.",
    "S013": "Over-reliance on Broad inflates irrelevant queries. Over-reliance on Exact caps volume. Balance is key.",
    "S014": "Mobile often converts at lower rates than Desktop. Without device adjustments, budget overflows to poor-converting devices.",
    "S015": "Demographic segmentation enables performance-based bidding by age group and gender.",
    "S016": "Geographic performance varies. Location adjustments based on ROAS by region improve overall efficiency.",
    "S017": "Flat budget distribution ignores performance signals. High-ROAS campaigns should receive more budget.",
    "S018": "PMAX tends to absorb budget from Search and Shopping if unchecked. Intentional channel allocation is required.",
    "S019": "Demand Gen campaigns build awareness and fill the top of the funnel.",
    "S020": "Remarketing captures high-intent users who already engaged with the brand, converting at higher rates.",
    "S021": "Optimized Targeting overrides the defined audience and serves to broad match — wasting budget on irrelevant users.",
}
