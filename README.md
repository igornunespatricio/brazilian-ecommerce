# Brazilian E-Commerce (Olist) — ETL Pipeline & Analytics

An end-to-end data engineering project built on Databricks: a medallion-architecture ETL pipeline (bronze → staging → gold) over the [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), orchestrated as code, validated by automated data quality checks at every layer, and feeding a scheduled executive-summary dashboard.

## Overview

This project takes raw CSV exports from a Brazilian e-commerce marketplace (orders, customers, products, sellers, payments, reviews, geolocation) and transforms them into a clean, modeled gold layer ready for analytics — with the full pipeline deployed, scheduled, quality-checked, and version-controlled using Databricks Asset Bundles.

**Stack:** PySpark, Databricks (Unity Catalog, Lakeflow Jobs, Lakeview Dashboards), Databricks Asset Bundles, SQL

## Architecture

```
Raw CSVs (Volumes)
      │
      ▼
┌─────────────┐  ┌────┐  ┌──────────────┐  ┌────┐  ┌─────────────┐  ┌────┐
│   Bronze    │─▶│ DQ │─▶│   Staging    │─▶│ DQ │─▶│    Gold     │─▶│ DQ │─▶ Dashboard
│ (raw, as-is)│  │    │  │ (typed, PK/  │  │    │  │ (business   │  │    │
│             │  │    │  │  FK, clean)  │  │    │  │  aggregates)│  │    │
└─────────────┘  └────┘  └──────────────┘  └────┘  └─────────────┘  └────┘
```

- **Bronze**: raw CSVs loaded as-is, all columns as strings, with a `_loaded_at` audit timestamp. No transformations — this layer exists to preserve the original data exactly as received.
- **Staging**: one table per source entity (customers, sellers, orders, order items, payments, reviews, products, category translation, geolocation), with proper types, primary/foreign key constraints, cleaned text fields, and derived columns (e.g. delivery delay flags, hours between order milestones).
- **Gold**: denormalized, business-ready tables answering specific analytical questions — sales summary, revenue by category/seller, delivery performance, customer lifetime value, product and category review performance.
- **DQ (Data Quality)**: a validation gate after each layer, logging results to an auditable table and halting the pipeline on critical failures before bad data propagates further downstream.

## Gold Layer

| Table | Grain | Purpose |
|---|---|---|
| `gold_sales_summary` | 1 row per order | Core fact table: revenue, payment, delivery status per order |
| `gold_revenue_by_category_month` | category × month | Revenue trend by product category over time |
| `gold_revenue_by_seller` | 1 row per seller | Seller revenue and delivery/shipping punctuality |
| `gold_delivery_performance` | 1 row per month | Monthly on-time/delayed delivery rates and step-by-step timing |
| `gold_delivery_by_region` | 1 row per customer state | Delivery speed and delay rate by region |
| `gold_customer_summary` | 1 row per unique customer | Order count, lifetime spend, review behavior, purchase dates |
| `gold_product_performance` | 1 row per product | Units sold, revenue, review score, delivery days |
| `gold_category_review_scores` | 1 row per category | Review score distribution and low-review share by category |

Full design rationale, including column definitions and key modeling decisions, is in [`docs/gold_layer_design.md`](docs/gold_layer_design.md).

### Key modeling decisions

- **Shared-blame attribution**: several metrics (seller delay rate, product review score, category review score) are computed only from orders where a single seller/product/category was involved. A multi-seller or multi-product order can't fairly attribute a delay or a bad review to any one party, so those metrics are deliberately scoped to unambiguous cases rather than spreading blame across everyone involved.
- **Null-safe percentages**: rate columns (`pct_delayed`, `pct_on_time`, etc.) return `null`, not `0`, when there's no underlying data — a 0% delay rate and "no completed orders yet" are different facts and shouldn't look the same.
- **Monetary precision**: currency columns use `decimal(10,2)` rather than `double`, to avoid floating-point rounding drift when aggregating revenue.

## Data Quality

Every layer transition is followed by an automated validation step rather than relying on manual spot-checks. Results are logged to `brazilian_ecommerce.prod.data_quality_log` — every check run (pass or fail, with row counts and details) is recorded there, giving an auditable history of data health over time, not just a pass/fail signal at run time.

| Layer | Checks | Examples |
|---|---|---|
| Bronze | Row count sanity | Each raw table has at least 1 row after load |
| Staging | Primary key uniqueness, not-null on PK columns, foreign key integrity (anti-join against the referenced table) | `staging_orders.order_id` is unique; every `staging_order_items.product_id` exists in `staging_products` |
| Gold | Domain/range checks, cross-table reconciliation | `review_score` between 1–5; `pct_delayed` between 0–1; total revenue matches between `gold_sales_summary` and `gold_revenue_by_category_month` |

**Design choices:**
- **`raise_on_failure` flag**: each check can either log-and-continue or log-and-halt the pipeline. Structural checks that would silently corrupt every downstream join or metric (PK uniqueness, FK integrity, domain ranges, reconciliation) are set to raise, stopping the job before bad data reaches the dashboard.
- **Databricks' declared PK/FK constraints are informational only** — they document intent but aren't enforced at write time, so a violating write would otherwise succeed silently. The data quality layer provides the actual enforcement these constraints imply but don't deliver on their own.
- **Gate placement**: `dq_bronze_checks`, `dq_staging_checks`, and `dq_gold_checks` run as their own tasks in the job graph — staging tasks depend on `dq_bronze_checks`, gold tasks depend on `dq_staging_checks`, and the dashboard refresh depends on `dq_gold_checks`. Nothing downstream runs on data that hasn't been validated.

Implementation lives in `src/data_quality/`: `dq_utils.py` holds the shared check functions (`check_not_null`, `check_unique`, `check_no_orphans`, `check_value_in_range`, `check_row_count_above`) and the logging helper; `bronze_checks.ipynb`, `staging_checks.ipynb`, and `gold_checks.ipynb` apply them per layer.

## Orchestration

The full pipeline — landing → bronze → DQ → staging → DQ → gold → DQ → dashboard refresh — runs as a single Databricks Job, defined as code via a [Databricks Asset Bundle](https://docs.databricks.com/en/dev-tools/bundles/) (`databricks.yml` + `resources/`).

- Tasks are wired by actual data dependency (e.g. `gold_sales_summary` depends only on `staging_orders`, `staging_order_items`, and `staging_order_payments` — not on every staging table), so independent tasks run in parallel rather than one long sequential chain.
- Scheduled to run daily; the dashboard refresh task runs as the final step, depending on `dq_gold_checks`, so it only fires once the full gold layer has rebuilt *and* passed validation — not on a separately guessed time delay, and not on unverified data.
- Deployed with `databricks bundle deploy`; the dashboard itself is version-controlled as a `.lvdash.json` file and kept in sync with `databricks bundle generate dashboard`.

## Dashboard

A Databricks Lakeview executive-summary dashboard built on the gold layer, covering:
- Headline KPIs (total revenue, total orders, % on-time delivery, repeat customer rate)
- Monthly revenue and delivery performance trends
- Category and regional breakdowns
- Top/bottom product and seller performance tables

Full widget list and underlying SQL queries are documented in [`docs/dashboard_design.md`](docs/dashboard_design.md).

## Project Structure

```
.
├── databricks.yml              # Bundle root config
├── resources/                  # Job and dashboard resource definitions (YAML)
├── dashboard/                  # Dashboard .lvdash.json definition
├── src/
│   ├── landing_to_bronze       # Raw CSV ingestion
│   ├── bronze_to_staging/      # One notebook per entity
│   ├── staging_to_gold/        # One notebook per gold table
│   └── data_quality/           # Shared check functions + one notebook per layer
├── docs/                       # Design docs: gold layer, dashboard
├── EDA/                        # Exploratory analysis
└── scripts/
```

## Running Locally

1. Install the [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/install.html) (v0.218.0+)
2. Authenticate: `databricks auth login --host <your-workspace-url>`
3. From the project root: `databricks bundle validate`
4. Deploy: `databricks bundle deploy -t dev`
5. Run: `databricks bundle run etl_pipeline -t dev`

## Possible Next Steps

- **Data quality dashboard**: a small dashboard/widget over `data_quality_log` itself, surfacing check pass rates and failure trends over time, rather than only seeing results in job logs
- **Alerting**: a Slack/email notification task on job failure, so a failed quality gate or pipeline run doesn't go unnoticed until someone checks manually
- **Incremental processing**: this dataset is a static sample with no reliable change-tracking timestamp, so every run does a full overwrite. A production version would use `MERGE INTO` / CDC-style loading against a source with proper change timestamps
- **Automated testing**: unit tests for transformation logic against small hand-crafted sample DataFrames
- **CI/CD**: a GitHub Actions workflow to run `bundle validate`/`bundle deploy` automatically on push

## Data Source

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — real (anonymized) commercial orders made at the Olist Store, Kaggle.