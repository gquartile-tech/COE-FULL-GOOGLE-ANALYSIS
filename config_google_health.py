"""
config_google_health.py
Control definitions for the Google CoE Account Health pillar.
23 controls: H001-H023.
H021, H022, H023 are manual UI checks — hardcoded OK in the rules engine.
"""
from __future__ import annotations
from config import STATUS_OK, STATUS_FLAG, STATUS_PARTIAL, ControlResult

PILLAR = "google_health"
SCORING_EXCLUDED = {"H021", "H022", "H023"}  # manual UI-only controls
MAX_FINDINGS = 24

PRIORITY_POINTS = {10: -18, 9: -15, 8: -13, 7: -11, 6: -9, 5: -7, 4: -5, 3: -3, 2: -2, 1: 0}
IMPACT_LABEL    = {10: "Critical", 9: "High", 8: "High", 7: "Medium", 6: "Medium",
                   5: "Medium",   4: "Low",  3: "Low",  2: "Visibility", 1: "Visibility"}

IMPORTANCE = {
    "H001": 9,  "H002": 8,  "H003": 9,  "H004": 8,  "H005": 8,
    "H006": 6,  "H007": 6,  "H008": 7,  "H009": 7,  "H010": 7,
    "H011": 7,  "H012": 7,  "H013": 6,  "H014": 6,  "H015": 6,
    "H016": 6,  "H017": 10, "H018": 9,  "H019": 7,  "H020": 6,
    "H021": 8,  "H022": 9,  "H023": 7,
}

CONTROL_NAMES = {
    "H001": "ROAS vs Target",
    "H002": "Spend Pacing vs Monthly Budget",
    "H003": "Revenue (AdSales) YoY",
    "H004": "Orders / Conversions YoY",
    "H005": "ACoS Trend YoY",
    "H006": "CPC Trend YoY",
    "H007": "CTR Trend YoY",
    "H008": "Conversion Rate Trend YoY",
    "H009": "MoM Revenue Trend (L3M)",
    "H010": "MoM ACoS Trend (L3M)",
    "H011": "PMAX Shopping Spend Share",
    "H012": "Channel Type Mix",
    "H013": "Zero-Spend Active Campaign Rate",
    "H014": "Price Competitiveness Score",
    "H015": "Top 5 Products Revenue Concentration",
    "H016": "Device Performance Split",
    "H017": "Billing Status",
    "H018": "Churn Risk Signal",
    "H019": "QR Score",
    "H020": "MRR vs Monthly Budget Ratio",
    "H021": "Conversion Tag Health",
    "H022": "GMC + GA4 Connection",
    "H023": "Product Disapproval Rate",
}

WHY = {
    "H001": "ROAS is the primary efficiency signal. Consistent underperformance vs target means the account is not meeting the client goal.",
    "H002": "Underpacing wastes opportunity. Overpacing risks the client overspending their budget. Both signal budget management issues.",
    "H003": "YoY removes seasonality distortion. It is the most reliable signal of structural revenue performance.",
    "H004": "Order volume isolates demand independent of pricing. A drop in orders is a pure demand signal.",
    "H005": "ACoS efficiency is the core profitability signal. Rising ACoS YoY means the account is becoming less efficient over time.",
    "H006": "CPC inflation is the primary indicator of auction pressure. Rising CPC with flat CVR directly compresses ROAS.",
    "H007": "CTR decline signals creative fatigue, ad relevance issues, or competitive displacement in the auction.",
    "H008": "CVR is the clearest signal of landing page or audience quality. Declining CVR inflates CPA regardless of bidding.",
    "H009": "MoM trend catches short-term deterioration before it shows in YoY. Three consecutive down months is a structural flag.",
    "H010": "Rising ACoS across 3 months signals compounding efficiency erosion, not a one-time fluctuation.",
    "H011": "PMAX campaigns should be Shopping-dominant. High Display or Video spend without Shopping signals misallocation.",
    "H012": "A healthy e-commerce account needs an intentional channel mix. Overconcentration in one type creates structural risk.",
    "H013": "Active campaigns with zero spend indicate structural issues: paused bids, exhausted budgets, disapprovals, or feed errors.",
    "H014": "Products priced above benchmark lose Shopping impressions and clicks. Price gap is a direct ROAS driver.",
    "H015": "High product concentration exposes the account to SKU-level risk. One top product going out of stock collapses revenue.",
    "H016": "Strong mobile spend with low conversions signals device bid adjustments are missing or need correction.",
    "H017": "A billing issue pauses the account. Early detection prevents campaign downtime and protects the client relationship.",
    "H018": "Churn risk flags from CS are the earliest available warning signal before performance issues escalate.",
    "H019": "QR Score is the standardized health signal from the last client review. A low score signals unresolved strategic gaps.",
    "H020": "An MRR fee disproportionately high vs the managed budget flags a structural profitability issue for the client.",
    "H021": "Without working conversion tracking, Smart Bidding has no signal and campaigns optimize blindly.",
    "H022": "GMC feeds Shopping campaigns. GA4 provides total sales and audience signals. Both disconnected means a blind account.",
    "H023": "Disapproved products cannot serve ads. Above 30% disapprovals significantly limits account scale and revenue.",
}

SOURCES = {
    "H001": "22_Client_Success[Primary_Spend_KPI__c, acos] + 02_Date_Range_KPIs[AdSpend, AdSales]",
    "H002": "02_Date_Range_KPIs[AdSpend] + 22_Client_Success[Monthly_Budget__c, Monthly_Budget_*__c]",
    "H003": "03_Yearly_KPIs[AdSales row — ThisPeriod, PreviousPeriod, YoY]",
    "H004": "03_Yearly_KPIs[Orders row — ThisPeriod, PreviousPeriod, YoY]",
    "H005": "03_Yearly_KPIs[ACoS row — ThisPeriod, PreviousPeriod, YoY]",
    "H006": "03_Yearly_KPIs[CPC row — ThisPeriod, PreviousPeriod, YoY]",
    "H007": "03_Yearly_KPIs[CTR row — ThisPeriod, PreviousPeriod, YoY]",
    "H008": "03_Yearly_KPIs[CR row — ThisPeriod, PreviousPeriod, YoY]",
    "H009": "04_L24M_Monthly_Performance_Sum[Month, AdSales]",
    "H010": "04_L24M_Monthly_Performance_Sum[Month, ACoS]",
    "H011": "18_PMAX_Channels[FieldType, Cost]",
    "H012": "07_Campaigns_by_Channel_Type[AdvertisingChannelType, Spend, Perc_Spend]",
    "H013": "13_Campaign_Gold_Metrics[CampaignId, Cost] + 38_Google_Campaign_Settings[Status]",
    "H014": "20_Price_Competitiveness[price, benchmark_price, price_gap_perc]",
    "H015": "08_Product_Shopping_Report[ProductItemId, Sales]",
    "H016": "16_Device_Breakdown[Device, Spend, Orders, Sales]",
    "H017": "15_Stripe_and_Account_Info[status, status_invoice, last_payment]",
    "H018": "22_Client_Success[CSM_Churn_Risk__c, Customer_Risk__c, Account_Risk_Score__c]",
    "H019": "22_Client_Success[Most_Recent_Past_QR_Score__c, Current_QR_Score__c]",
    "H020": "22_Client_Success[MRR__c, Monthly_Budget__c]",
    "H021": "MANUAL — Google Ads UI: Tools > Conversions",
    "H022": "40_Google_Account_Links[MerchantStatus, AnalyticsStatus] + 34_Google_Advertiser_Details[GMC_Linked]",
    "H023": "MANUAL — Google Merchant Center: Overview > Products Dashboard",
}
