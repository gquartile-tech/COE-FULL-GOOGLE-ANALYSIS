"""
config_google_implementation.py
26 controls: I001-I026
Many controls require Google Ads UI — those are hardcoded OK with reviewer notes.
Auto-evaluatable: I001, I003 (proxy), I004, I009, I011, I013 (partial), I016 (partial), I022 (partial).
"""
from __future__ import annotations
from config import STATUS_OK, STATUS_FLAG, STATUS_PARTIAL, ControlResult

PILLAR = "google_implementation"
SCORING_EXCLUDED = {  # manual UI-only controls
    "I002", "I005", "I006", "I007", "I008", "I010",
    "I012", "I014", "I015", "I017", "I018", "I019", "I020", "I021",
    "I023", "I024", "I025", "I026",
}
MAX_FINDINGS = 20

PRIORITY_POINTS = {10: -18, 9: -15, 8: -13, 7: -11, 6: -9, 5: -7, 4: -5, 3: -3, 2: -2, 1: 0}
IMPACT_LABEL    = {10: "Critical", 9: "High", 8: "High", 7: "Medium", 6: "Medium",
                   5: "Medium",   4: "Low",  3: "Low",  2: "Visibility", 1: "Visibility"}

IMPORTANCE = {
    "I001": 8, "I002": 9, "I003": 10, "I004": 10, "I005": 9,
    "I006": 8, "I007": 7, "I008": 8,  "I009": 7,  "I010": 7,
    "I011": 7, "I012": 6, "I013": 5,  "I014": 7,  "I015": 8,
    "I016": 5, "I017": 8, "I018": 7,  "I019": 6,  "I020": 7,
    "I021": 7, "I022": 6, "I023": 7,  "I024": 5,  "I025": 4,
    "I026": 5,
}

CONTROL_NAMES = {
    "I001": "Salesforce Access Confirmed",
    "I002": "GMC + GA4 Linked to Google Ads",
    "I003": "Conversion Tag Active & Firing",
    "I004": "Billing Status Active",
    "I005": "Policy Violations = Zero",
    "I006": "Product Disapproval Rate < 10%",
    "I007": "GMC Feed Duplication Check",
    "I008": "Quartile Portal Feed Active",
    "I009": "Shopify / E-commerce Platform Connected",
    "I010": "Data Sources Confirmed in Google Ads",
    "I011": "Naming Conventions (QT Standard)",
    "I012": "Location Targeting Set to Presence Only",
    "I013": "Location Segmentation by State/Region",
    "I014": "Auto-Apply Recommendations Disabled",
    "I015": "Final URL Correct & Active",
    "I016": "Promotion End Dates Correct",
    "I017": "PMAX Automation Settings Disabled",
    "I018": "PMAX Audiences Configured (min requirements)",
    "I019": "PMAX Search Themes Set (min 10)",
    "I020": "PMAX Images Present & Approved",
    "I021": "PMAX Listing Groups Eligible",
    "I022": "Shopping Campaign Priority Correct",
    "I023": "Negative Lists Created & Assigned",
    "I024": "Sitelink Extensions (min 4)",
    "I025": "Business Name Present",
    "I026": "Logo Asset Approved (min 1)",
}

WHY = {
    "I001": "Salesforce is the SSOT for client constraints, goals, and CS data. Inaccessible records break the agent pipeline.",
    "I002": "GMC feeds Shopping/PMAX product data. GA4 provides total sales and audience signals.",
    "I003": "Smart Bidding requires conversion signal. A broken tag means all automated bid strategies are flying blind.",
    "I004": "A billing failure pauses all campaigns immediately.",
    "I005": "Policy violations can trigger account suspension, ad disapprovals, and impression share loss at scale.",
    "I006": "Disapproved products cannot serve ads. Above 30% significantly caps account revenue potential.",
    "I007": "Duplicate feeds create product conflicts, attribute overwrites, and unpredictable disapprovals.",
    "I008": "If the QT feed pipeline breaks, product titles and custom labels stop updating, degrading Shopping silently.",
    "I009": "Platform connection enables total sales tracking and TACoS calculation.",
    "I010": "Data source gaps create reporting blind spots and prevent Smart Bidding from receiving complete signals.",
    "I011": "Consistent naming enables automated parsing, reporting segmentation, and campaign identification.",
    "I012": "Presence+Interest serves ads to users who searched for a location but aren't physically there.",
    "I013": "Geographic segmentation enables performance-based bid adjustments by region.",
    "I014": "Auto-apply can make unwanted structural changes that undermine Quartile's strategy.",
    "I015": "Broken Final URLs result in ad disapprovals, wasted clicks, and zero conversions.",
    "I016": "Expired promotions still serving mislead users and can violate Google's promotional content policies.",
    "I017": "Unconfigured PMAX automations allow Google to expand targeting outside intended audiences.",
    "I018": "Underpopulated PMAX audience signals force Google to broad-match audiences using only product data.",
    "I019": "Too few Search Themes limit PMAX intent targeting in the Search channel.",
    "I020": "PMAX without images defaults to text-only ads across Display, Gmail, and YouTube.",
    "I021": "Ineligible listing groups mean products are silently excluded from PMAX Shopping inventory.",
    "I022": "Incorrect priority settings cause wrong campaigns to win auctions, disrupting the CWCD funnel.",
    "I023": "Campaigns without negatives have uncontrolled query routing and irrelevant traffic.",
    "I024": "Fewer than 4 sitelinks reduce ad real estate and limit navigation for high-intent users.",
    "I025": "Missing business name reduces ad credibility and quality signals.",
    "I026": "Missing logos default PMAX Display ads to text-only, reducing brand presence.",
}
