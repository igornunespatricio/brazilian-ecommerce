# Executive Summary Dashboard — Brazilian E-Commerce (Olist)

This document outlines the design for a Databricks Lakeview dashboard built on top of the gold layer (`brazilian_ecommerce.prod.gold_*` tables). It covers the dashboard structure, each widget, its source table, and the SQL query behind it.

---

## Layout & Widgets

### Section 1 — Headline KPIs (counters)

| Widget | Metric | Source |
|---|---|---|
| Total Revenue | Sum of order revenue | `gold_sales_summary` |
| Total Orders | Count of orders | `gold_sales_summary` |
| % Delivered On Time | On-time orders / total delivered orders | `gold_sales_summary` |
| Avg Review Score | Average review score across categories | `gold_category_review_scores` |
| Repeat Customer Rate | % of customers with more than one order | `gold_customer_summary` |

**% Delivered On Time**
```sql
SELECT
  ROUND(
    COUNT(CASE WHEN delivery_status = 'on_time' THEN 1 END)
    / COUNT(CASE WHEN delivery_status IS NOT NULL THEN 1 END),
    4
  ) AS pct_delivered_on_time
FROM brazilian_ecommerce.prod.gold_sales_summary
```

**Total Revenue / Total Orders**
```sql
SELECT
  SUM(total_order_value) AS total_revenue,
  COUNT(DISTINCT order_id) AS total_orders
FROM brazilian_ecommerce.prod.gold_sales_summary
```

**Repeat Customer Rate**
```sql
SELECT
  ROUND(
    COUNT(CASE WHEN total_orders > 1 THEN 1 END) / COUNT(*),
    4
  ) AS repeat_customer_rate
FROM brazilian_ecommerce.prod.gold_customer_summary
```

---

### Section 2 — Trends (line charts, tables with `year_month`)

| Widget | Source |
|---|---|
| Monthly Revenue by Category | `gold_revenue_by_category_month` |
| Monthly % On-Time vs % Delayed | `gold_delivery_performance` |

**Monthly Revenue (all categories combined)**
```sql
SELECT
  year_month,
  SUM(total_revenue) AS total_revenue
FROM brazilian_ecommerce.prod.gold_revenue_by_category_month
GROUP BY year_month
ORDER BY year_month
```

**Monthly % On-Time vs % Delayed**
```sql
SELECT
  year_month,
  pct_on_time,
  pct_delayed
FROM brazilian_ecommerce.prod.gold_delivery_performance
ORDER BY year_month
```

---

### Section 3 — Breakdowns (bar charts, no time dimension)

| Widget | Source |
|---|---|
| Avg Review Score by Category | `gold_category_review_scores` |
| Avg Delivery Days by State | `gold_delivery_by_region` |
| % Delayed Orders by State | `gold_delivery_by_region` |

**Avg Review Score by Category**
```sql
SELECT
  product_category_name_english,
  avg_review_score,
  total_reviews
FROM brazilian_ecommerce.prod.gold_category_review_scores
ORDER BY avg_review_score ASC
```

**Delivery Performance by State**
```sql
SELECT
  customer_state,
  avg_delivery_days,
  pct_delayed,
  total_orders
FROM brazilian_ecommerce.prod.gold_delivery_by_region
ORDER BY pct_delayed DESC
```

---

### Section 4 — Top / Bottom Performers (tables)

| Widget | Source |
|---|---|
| Top 10 Products by Revenue | `gold_product_performance` |
| Bottom 10 Products by Review Score | `gold_product_performance` |
| Top 10 Sellers by Revenue | `gold_revenue_by_seller` |

**Top 10 Products by Revenue**
```sql
SELECT
  product_id,
  product_category_name_english,
  total_units_sold,
  total_revenue,
  avg_review_score
FROM brazilian_ecommerce.prod.gold_product_performance
ORDER BY total_revenue DESC
LIMIT 10
```

**Bottom 10 Products by Review Score**
```sql
SELECT
  product_id,
  product_category_name_english,
  avg_review_score,
  total_units_sold
FROM brazilian_ecommerce.prod.gold_product_performance
WHERE avg_review_score IS NOT NULL
ORDER BY avg_review_score ASC
LIMIT 10
```

**Top 10 Sellers by Revenue**
```sql
SELECT
  seller_id,
  total_revenue,
  total_orders,
  pct_delayed_orders,
  pct_shipped_late_single_seller
FROM brazilian_ecommerce.prod.gold_revenue_by_seller
ORDER BY total_revenue DESC
LIMIT 10
```

---

## Notes & Caveats

- **Tables without a `year_month` column** (`gold_product_performance`, `gold_revenue_by_seller`, `gold_category_review_scores`, `gold_delivery_by_region`, `gold_customer_summary`) are current full-history snapshots, not time series — they belong in the Breakdown/Top-Bottom sections, not the Trend section.
- **Sample size caveats carry over from the gold layer**: several percentage metrics (`pct_delayed_orders`, `pct_shipped_late_single_seller`, review scores) are restricted to single-seller or single-product/category orders to avoid shared-blame attribution issues — small sample sizes per entity should be interpreted with that in mind. Consider adding a minimum-order-count filter to the Top/Bottom tables if noisy low-volume entities show up at the extremes.
- **Refresh schedule**: since gold tables are rebuilt via `overwrite`, the dashboard should be scheduled to refresh after the ETL pipeline completes, not on an independent schedule that might run against a stale or half-rebuilt table.