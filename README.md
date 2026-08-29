# CMS Hospital Performance Platform

A data platform that combines two CMS healthcare datasets:

- **CMS Hospital Value-Based Purchasing (HVBP)** — financial and hospital performance data
- **CMS Inpatient Quality Reporting (IQR)** — Emergency Department performance data

The project puts both datasets through one ingestion system, stores them in a dbt data warehouse, and provides a FastAPI read API and Power BI dashboards.

The project also identifies and fixes a real hospital ID data problem and performs an analysis comparing Emergency Department boarding time with HVBP performance.

---

## Architecture

```text
CMS HVBP                         CMS IQR Emergency Department Data
     |                                      |
     |                              PySpark processing
     |                                      |
     +---------------+----------------------+
                     |
                     v
             Config-driven loader
              (ingest/loader.py)
                     |
          Two YAML source configurations
          - cms_hvbp.yml
          - cms_iqr.yml
                     |
                     v
              Bronze CSV layer
                     |
                     v
                dbt staging
                     |
                     v
             dbt intermediate
                     |
                     v
                 dbt marts
                     |
                     v
              FastAPI read API
                     |
                     v
               Power BI dashboards
```

The ingestion system uses one loader for both datasets. The YAML configuration files define things such as data types, validation rules, and output locations.

dbt uses **DuckDB by default**, so the entire warehouse can be built locally without credentials.

Snowflake is also documented as an alternative database. The main models after the staging layer are designed to work with either warehouse.

---

# Main Finding

The project compares Emergency Department boarding time with the hospital's HVBP Total Performance Score (TPS).

There is no CMS measure specifically called "boarding time." This project uses **OP_18d**, which measures the median number of minutes before a patient is transferred to another facility, as a proxy for boarding time.

Hospitals were divided into four groups based on their boarding time:

| Group | Average Boarding Time | Average TPS | Hospitals |
|---|---:|---:|---:|
| Q1 — Fastest | 233 min | 33.07 | 270 |
| Q2 | 301 min | 33.36 | 271 |
| Q3 | 360 min | 33.96 | 270 |
| Q4 — Slowest | 489 min | 31.78 | 268 |

The Spearman correlation was:

**ρ = −0.0254, p = 0.40**

This means there was **no meaningful relationship** between ED boarding time and the overall HVBP Total Performance Score in FY2026.

The average TPS was relatively flat across the groups:

**33.1 → 33.4 → 34.0 → 31.8**

So the data does not show that hospitals with longer ED boarding times necessarily have lower or higher HVBP scores.

This is a reasonable finding because ED throughput is not directly one of the HVBP scoring categories.

The analysis includes **1,079 hospitals** that had both metrics available.

> This is a correlation analysis using one fiscal year of data. It does not prove that ED performance causes changes in reimbursement.

Run the analysis with:

```bash
python -m cms_platform.analysis.ed_hvbp_finding
```

Run this after completing the dbt build.

---

# Data Model

The project uses a star-schema style data model.

### `dim_hospital`

Contains one row for each hospital CCN found in either dataset.

It also shows whether the hospital appears in:

- HVBP data
- ED data

This makes it possible to see missing coverage instead of automatically removing hospitals through an inner join.

### `dim_measure`

Contains the measures from both datasets:

- 7 Emergency Department measures
- 5 HVBP domain/total scores

It also stores:

- Measure domain
- Whether higher or lower values are better
- Unit of measurement

### `dim_fiscal_period`

Contains fiscal-year information.

The model is designed to support different performance periods and lag years.

The current project contains only FY2026 HVBP data, so the lag structure cannot yet be demonstrated across multiple years.

The ED reporting periods come directly from the data:

- EDV / OP_22 → calendar year 2024
- OP_18a–d / OP_23 → approximately July 2024 through June 2025

### Fact Tables

The project contains:

- `fact_ed_measure`
- `fact_hvbp_domain_score`
- `fact_hvbp_performance`

These store hospital-level measurements and scores.

### `mart_ed_performance_vs_hvbp`

This is the main analysis table.

It combines:

- ED measures
- HVBP total score
- HVBP domain scores
- Boarding-time rankings
- Hospital peer information

---

# Boarding Time Measure

CMS does not provide a measure literally named "boarding time" in this dataset.

This project uses:

**OP_18d — median minutes before transfer to another facility**

as a boarding-time proxy.

The reason is that patients waiting for transfer to another facility are effectively waiting in the ED for their next placement.

This is a **project modeling decision**, not an official CMS definition.

---

# Synthetic Financial Estimate

The field:

```text
estimated_dollar_impact_synthetic
```

is **not actual CMS payment data**.

It is a project assumption based on:

1. HVBP Total Performance Score quartiles
2. The actual FY2026 score distribution
3. An assumed $10 million Medicare base revenue per hospital

The value is clearly labeled as synthetic and is never presented as an actual payment amount.

The field:

```text
payment_adjustment_factor
```

is currently `null`.

It exists so that the real CMS payment adjustment factor can be added later without changing the database structure.

---

# Data Limitations

There are several important limitations.

### 1. Only one HVBP fiscal year

The project currently uses FY2026 data.

A multi-year analysis will require additional HVBP years.

### 2. ED data is limited

The IQR data currently includes:

- EDV
- OP_18a
- OP_18b
- OP_18c
- OP_18d
- OP_22
- OP_23

Other IQR measures are not included.

### 3. Real payment adjustment data is not included

The actual CMS payment adjustment factor is not loaded.

Instead:

```text
payment_adjustment_factor = null
```

and the synthetic estimate is clearly labeled as an assumption.

### 4. Some fiscal-period dates are approximate

The exact CMS performance periods for some HVBP domains are not reproduced in this project.

### 5. Boarding time is a proxy

OP_18d is being used as a proxy for boarding time. It is not an official CMS boarding-time metric.

### 6. The analysis is correlational

The analysis uses one fiscal year and does not establish causation.

It does **not** show that ED performance causes reimbursement changes.

---

# Engineering

## Fixing the CCN Bug

One important bug was found and fixed in the original data pipeline.

CMS hospital IDs are called **CCNs** and should contain six characters.

For example:

```text
010001
```

The original loader used:

```python
pd.read_csv()
```

without specifying the data type.

Because CMS provided the ID as:

```text
010001
```

Pandas interpreted it as a number:

```text
10001
```

The leading zero was lost.

This caused hospital IDs to stop matching the six-character CCNs in the other dataset.

### The Fix

The project protects the CCN in three places.

**1. During ingestion**

The loader reads the hospital ID as a string instead of a number.

```text
dtype_hint: str
```

This prevents the leading zero from being removed.

**2. During Bronze-layer reading**

DuckDB also reads the CCN as a `VARCHAR`.

**3. During dbt staging**

The staging models use:

```sql
LPAD(ccn, 6, '0')
```

This adds the missing leading zero if necessary.

This gives the project multiple layers of protection against the same problem.

---

# Testing the Bug Fix

The tests verify that the CCN remains correct.

For example:

```text
010001
```

must remain:

```text
010001
```

rather than becoming:

```text
10001
```

Tests include:

```text
test_ccn_leading_zero_survives_naive_pandas_read_when_dtype_forced
```

and:

```text
test_full_ingest_path_preserves_ccn
```

The dbt model also checks that every CCN contains exactly six characters.

---

# Impact of the Bug Fix

After fixing the CCN issue:

**2,451 of the 2,455 HVBP hospitals** were successfully matched with hospitals in the ED dataset.

The ED dataset contains approximately **4,660 hospitals**.

Before the fix, IDs such as:

```text
10001
```

could not correctly match:

```text
010001
```

The improved overlap demonstrates that the bug had a real impact on the data pipeline.

---

# Config-Driven Data Ingestion

Instead of creating a separate ingestion script for every dataset, the project uses:

```text
ingest/loader.py
```

with two configuration files:

```text
config/sources/cms_hvbp.yml
config/sources/cms_iqr.yml
```

The configuration files define:

- Data types
- Required fields
- Minimum and maximum values
- Validation rules
- Minimum row counts
- Output locations

The same loader can therefore process both sources.

This replaces separate, dataset-specific ingestion scripts with one reusable ingestion system.

---

# dbt

The dbt pipeline follows:

```text
Staging
   ↓
Intermediate
   ↓
Marts
```

The project uses dbt tests such as:

- `unique`
- `not_null`
- `accepted_values`
- `unique_combination_of_columns`
- `expression_is_true`
- `relationships`

There are currently:

**54 dbt tests**

and they pass successfully with:

```bash
dbt build
```

DuckDB is the default database and does not require credentials.

---

# Python Tests

The project also contains **20 pytest tests**.

They cover:

- Loader behavior
- Data validation
- CCN handling
- API behavior
- API integration

The API tests use a small test DuckDB database rather than requiring a complete production database.

Run:

```bash
pytest
```

---

# CI Pipeline

GitHub Actions runs automatically on every push.

The CI pipeline checks:

```text
ruff check
     ↓
Data loader
     ↓
pytest
     ↓
dbt deps
     ↓
dbt build
     ↓
API smoke test
```

This helps make sure that code changes do not break the ingestion pipeline, database models, tests, or API.

---

# API

The project provides a **FastAPI read API**.

The API includes:

- Async request handlers
- Pydantic request/response models
- Structured JSON logs
- Request IDs
- Request duration tracking
- Structured error responses
- TTL caching
- API-key authentication

Authentication uses:

```text
X-API-Key
```

There is no `/predict` endpoint because the project does not contain an ML model.

### Available Endpoints

```text
GET /health

GET /hospitals?state=NY&limit=50&offset=0

GET /hospitals/{ccn}

GET /hospitals/{ccn}/peers
```

Example:

```bash
curl -H "X-API-Key: dev-local-key" \
http://localhost:8000/hospitals/010001
```

Example response:

```json
{
  "ccn": "010001",
  "hospital_name": "SOUTHEAST HEALTH MEDICAL CENTER",
  "city": "DOTHAN",
  "state": "AL",
  "present_in_ed": true,
  "present_in_hvbp": true,
  "total_performance_score": 32.17,
  "synthetic_tier_label": "Average",
  "estimated_dollar_impact_synthetic": 0.0,
  "payment_adjustment_factor": null,
  "measures": [
    {
      "measure_id": "OP_18a",
      "reported_value": 218.0,
      "unit": "minutes",
      "direction": "lower_is_better"
    }
  ]
}
```

Other examples:

```bash
curl -H "X-API-Key: dev-local-key" \
"http://localhost:8000/hospitals?state=AL&limit=5"

curl -H "X-API-Key: dev-local-key" \
http://localhost:8000/hospitals/010001/peers
```

Invalid API keys return a structured `401` response.

Unknown hospital CCNs return a structured `404` response.

---

# Running the Project

## Option 1: Run Locally

Install the project:

```bash
pip install -e ".[dev]"
```

Run the data ingestion:

```bash
python -m cms_platform.ingest.loader
```

Build the dbt warehouse:

```bash
cd dbt
dbt deps --profiles-dir .
dbt build --profiles-dir .
cd ..
```

Start the API:

```bash
uvicorn cms_platform.api.main:app --reload
```

---

# Option 2: Run with Docker

The project also supports Docker Compose.

```bash
docker compose up
```

Docker will:

1. Run the data loader
2. Build the dbt warehouse
3. Store the database in a shared volume
4. Start the API

This means the project can be started from a clean clone without manually running each step.

---

# Useful Commands

Run the analysis:

```bash
python -m cms_platform.analysis.ed_hvbp_finding
```

Run tests:

```bash
pytest
```

Run linting:

```bash
ruff check src tests
```

---

# Dashboards

The project includes Power BI dashboards built from:

```text
mart_ed_performance_vs_hvbp
```

and the HVBP financial marts.

The Power BI file is:

```text
powerbi/healthcare.pbix
```

Dashboard exports are stored in:

```text
exports/
```

The dashboard is intentionally kept simple because the main focus of the project is the data platform underneath it.

---

# What This Project Demonstrates

This project demonstrates four main areas:

### Data Engineering

- PySpark
- dbt
- Config-driven ingestion
- Data validation
- Data lineage
- DuckDB
- Snowflake-ready architecture

### Backend Engineering

- FastAPI
- Async APIs
- Pydantic
- API authentication
- Structured errors
- Caching
- Docker
- CI/CD
- Automated testing

### Problem Solving

A real CCN data-quality bug was found, investigated, and fixed across multiple layers of the pipeline.

### Healthcare Data

The project works with real CMS hospital performance data and combines:

- HVBP performance
- ED throughput
- Hospital information
- Hospital peer comparisons

---

## In Simple Terms

The project takes **two different CMS hospital datasets**, cleans and validates them, makes sure hospitals can be matched correctly, stores the information in a structured database, and exposes the data through an API and dashboard.

The main analysis asks:

> **Do hospitals with longer ED boarding times have worse HVBP performance?**

For FY2026, the answer from this dataset is:

> **No meaningful relationship was found.**

The project is therefore primarily a **data engineering + backend platform**, with an analysis layer on top of it — not an ML prediction system.
