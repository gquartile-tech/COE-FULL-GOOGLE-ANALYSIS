# Google CoE Full Analysis Tool

Quartile Center of Excellence — Google Ads automated audit agent suite.

## What it does

Upload one Google Databricks pre-analysis export (.xlsx / .xlsm).  
Five agents run sequentially and produce five scored `.xlsm` output files:

| Pillar | Controls | Key data sources |
|---|---|---|
| Health | 23 | KPI tabs, Stripe, Salesforce, PMAX channels |
| Mastery | 14 | Feed, DPL, Salesforce, Stripe |
| Framework | 42 | Campaign Settings (Tab 38), Search Terms, Feed, Channel mix |
| Strategy | 21 | Campaign names across Tabs 35/38/13 — reviewer-driven |
| Implementation | 26 | Billing, naming, location, asset groups, account links |

---

## Repo structure

```
app.py                              ← Flask backend, all 5 run_google_* functions
templates/index.html                ← Frontend UI
requirements.txt
Procfile
render.yaml

reader_databricks_google.py         ← Shared reader for all pillars (all 40 tabs)
config.py                           ← Shared ControlResult dataclass + STATUS constants

config_google_health.py
rules_engine_google_health.py
writer_google_health.py

config_google_mastery.py
rules_engine_google_mastery.py
writer_google_mastery.py

config_google_framework.py
rules_engine_google_framework.py
writer_google_framework.py

config_google_strategy.py
rules_engine_google_strategy.py
writer_google_strategy.py

config_google_implementation.py
rules_engine_google_implementation.py
writer_google_implementation.py

templates/
  CoE_Google_Account_Health_Analysis_Templates.xlsm
  CoE_Account_Mastery_Analysis_Templates.xlsm         ← reuses Amazon Mastery template
  CoE_Google_Framework_Analysis_Templates.xlsm
  CoE_Google_Account_Strategy_Analysis_Templates.xlsm
  CoE_Google_Account_Implementation_Analysis_Templates.xlsm

uploads/    ← auto-created at runtime, auto-deleted after each run
outputs/    ← auto-created at runtime, stores generated .xlsm files
```

---

## config.py dependency

This repo requires `config.py` with the shared `ControlResult` dataclass.  
Copy it from the Amazon CoE repo. It must contain:

```python
from dataclasses import dataclass

STATUS_OK      = "OK"
STATUS_PARTIAL = "PARTIAL"
STATUS_FLAG    = "FLAG"

@dataclass(frozen=True)
class ControlResult:
    status: str
    what: str = ''
    why:  str = ''
    source: str = ''
```

---

## Deploy on Render

1. Push all files to a new GitHub repo.
2. Add the five `.xlsm` template files to `templates/`.
3. Connect the repo to a new Render Web Service.
4. Render auto-detects `render.yaml` — no manual config needed.
5. Service name: `google-coe-full-analysis`

### Healthcheck

```
GET /healthcheck
```

Returns `200 ok` if all 5 templates are present, `503 degraded` with a list of missing templates.

---

## Timeout note

All five agents run sequentially (not parallel).  
Gunicorn timeout is set to 500 seconds — sufficient for large accounts on Render's free tier.  
If a single account exceeds this, increase `--timeout` in `Procfile` and `render.yaml`.

---

## Data source reference

All tabs use header row index 5 (0-based), hard-locked in `reader_databricks_google.py`.  
Tab registry lives in `TAB_KEYS` dict — prefix-matched so minor tab name changes don't break the agent.

| Tab | Content | Primary pillar users |
|---|---|---|
| 02 | Date Range KPIs | Health, Framework |
| 03 | Yearly KPIs YoY | Health, Framework |
| 04 | L24M Monthly | Health |
| 07 | Channel Type mix | Health, Framework, Strategy |
| 08 | Product Shopping | Health |
| 09 | Keyword Report | Framework, Strategy |
| 11 | Search Terms | Framework |
| 13 | Campaign Gold Metrics | Framework, Strategy |
| 15 | Stripe & Account Info | Mastery, Implementation |
| 16 | Device Breakdown | Health, Framework |
| 17 | Product Monthly KPIs | — |
| 18 | PMAX Channels | Health, Framework |
| 20 | Price Competitiveness | Health, Mastery, Framework |
| 22 | Client Success (SF) | All pillars |
| 26 | Location Performance | Framework, Strategy |
| 28 | DPL Performance | Mastery, Framework |
| 30 | Feed Products | Mastery, Framework |
| 31 | Negative Keywords | Framework |
| 32 | Asset Groups | Framework, Implementation |
| 33 | Assets Extensions | Framework, Implementation |
| 34 | Advertiser Details | Health, Implementation |
| 35 | Campaigns V2 Enriched | Framework, Strategy |
| 38 | Campaign Settings | Framework (primary) |
| 40 | Account Links | Health, Implementation |
