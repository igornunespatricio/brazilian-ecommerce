# Gold Layer Design — Brazilian E-Commerce (Olist)

This document outlines proposed gold tables for the `brazilian_ecommerce.prod` schema, built on top of the existing staging layer (`staging_customers`, `staging_orders`, `staging_order_items`, `staging_products`, `staging_sellers`, `staging_order_payments`, `staging_order_reviews`, `staging_geolocation`, `staging_category_translation`).

Each gold table is a denormalized fact or aggregate table, designed to answer a specific business question directly, without requiring further joins downstream.

---

## 1. Sales & Revenue

### `gold_sales_summary`
**Grain:** one row per order
**Purpose:** core fact table for revenue analysis; most other sales-related gold tables can be derived from this one.

**Sources:** `staging_orders` + `staging_order_items` + `staging_order_payments`

**Suggested columns:**
- `order_id`
- `customer_id`
- `order_status`
- `order_purchase_timestamp`
- `total_items` (count of order items)
- `total_price` (sum of item prices)
- `total_freight_value`
- `total_order_value` (price + freight)
- `payment_type` (primary/most common payment type used)
- `payment_installments` (max installments used)
- `delivery_status` (on_time / delayed)
- `hours_purchase_to_approved`, `hours_approved_to_carrier`, `hours_carrier_to_customer` (from staging_orders)

---

### `gold_revenue_by_category_month`
**Grain:** one row per product category + month
**Purpose:** revenue trend analysis over time by category.

**Sources:** `staging_order_items` + `staging_products` + `staging_category_translation` + `staging_orders` (for purchase date)

**Suggested columns:**
- `year_month`
- `product_category_name_english`
- `total_revenue`
- `total_orders`
- `total_units_sold`
- `avg_ticket_value`

---

### `gold_revenue_by_seller`
**Grain:** one row per seller
**Purpose:** seller performance ranking.

**Sources:** `staging_order_items` + `staging_sellers` + `staging_orders`

**Suggested columns:**
- `seller_id`
- `total_revenue`
- `total_orders`
- `avg_freight_value`
- `avg_delivery_days` (purchase to customer)
- `pct_delayed_orders`

---

## 2. Delivery & Logistics

### `gold_delivery_performance`
**Grain:** one row per month (or per month + state)
**Purpose:** operational dashboard tracking delivery speed and reliability over time.

**Sources:** `staging_orders`

**Suggested columns:**
- `year_month`
- `pct_on_time`
- `pct_delayed`
- `avg_hours_purchase_to_approved`
- `avg_hours_approved_to_carrier`
- `avg_hours_carrier_to_customer`
- `avg_hours_estimated_to_delivered`

---

### `gold_delivery_by_region`
**Grain:** one row per customer state (or city)
**Purpose:** identify regions with consistently slower or more delayed shipments.

**Sources:** `staging_orders` + `staging_customers` + `staging_geolocation` (aggregated by zip prefix)

**Suggested columns:**
- `customer_state`
- `total_orders`
- `avg_delivery_days`
- `pct_delayed`

---

## 3. Customer Analytics

### `gold_customer_summary`
**Grain:** one row per unique customer (`customer_unique_id`, not `customer_id`, since a person can have multiple `customer_id`s across orders)
**Purpose:** identify repeat buyers vs one-time buyers, customer lifetime value.

**Sources:** `staging_customers` + `staging_orders` + `staging_order_payments` + `staging_order_reviews`

**Suggested columns:**
- `customer_unique_id`
- `total_orders`
- `total_spend`
- `avg_review_score_given`
- `first_purchase_date`
- `last_purchase_date`
- `customer_state`

---

### `gold_customer_geolocation`
**Grain:** one row per customer
**Purpose:** enable customer map visualizations.

**Sources:** `staging_customers` + `staging_geolocation` (aggregated avg lat/lng per zip prefix)

**Suggested columns:**
- `customer_id`
- `customer_zip_code_prefix`
- `avg_lat`
- `avg_lng`

---

## 4. Product & Reviews

### `gold_product_performance`
**Grain:** one row per product
**Purpose:** identify best- and worst-performing products.

**Sources:** `staging_order_items` + `staging_products` + `staging_order_reviews` (via order_id) + `staging_orders`

**Suggested columns:**
- `product_id`
- `product_category_name_english`
- `total_units_sold`
- `total_revenue`
- `avg_review_score`
- `avg_delivery_days`

---

### `gold_category_review_scores`
**Grain:** one row per product category
**Purpose:** flag categories with quality/satisfaction issues.

**Sources:** `staging_order_reviews` + `staging_order_items` + `staging_products` + `staging_category_translation`

**Suggested columns:**
- `product_category_name_english`
- `total_reviews`
- `avg_review_score`
- `pct_low_reviews` (1–2 star share)

---

### `gold_review_sentiment_lag`
**Grain:** one row per review score (1–5)
**Purpose:** see if negative reviews get slower or faster responses.

**Sources:** `staging_order_reviews`

**Suggested columns:**
- `review_score`
- `avg_days_creation_to_answer`
- `total_reviews`

---

## 5. Payments

### `gold_payment_behavior`
**Grain:** one row per payment_type + installment count
**Purpose:** see if customers who pay in more installments spend more; understand payment method mix.

**Sources:** `staging_order_payments`

**Suggested columns:**
- `payment_type`
- `payment_installments`
- `total_orders`
- `avg_payment_value`
- `total_payment_value`

---

## Suggested Build Order

1. `gold_sales_summary` — central fact table, reused by most others
2. `gold_customer_summary`
3. `gold_product_performance`
4. `gold_delivery_performance` / `gold_delivery_by_region`
5. `gold_revenue_by_category_month` / `gold_revenue_by_seller`
6. `gold_category_review_scores` / `gold_review_sentiment_lag`
7. `gold_payment_behavior`
8. `gold_customer_geolocation`