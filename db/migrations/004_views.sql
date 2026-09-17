-- Read-only, least-privilege views per Technical Design Document
-- section 3.1. These are the only surface the agent-facing DB role
-- should ever query; they never expose payment instruments or raw
-- customer PII (email/phone are not present in the source dataset).
SET search_path TO shopops_views;

-- order ID, status, dates, delivery estimate, seller ID, payment summary
CREATE OR REPLACE VIEW vw_order_ops AS
SELECT
    o.order_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_estimated_delivery_date,
    o.order_delivered_customer_date,
    oi.seller_id,
    SUM(p.payment_value) AS order_value
FROM shopops_data.orders o
JOIN shopops_data.order_items oi USING (order_id)
LEFT JOIN shopops_data.order_payments p USING (order_id)
GROUP BY o.order_id, o.order_status, o.order_purchase_timestamp,
         o.order_estimated_delivery_date, o.order_delivered_customer_date,
         oi.seller_id;

-- pseudonymous customer key, aggregate purchase history, recent orders
CREATE OR REPLACE VIEW vw_customer_order_history AS
SELECT
    c.customer_unique_id,
    COUNT(DISTINCT o.order_id)         AS total_orders,
    SUM(p.payment_value)               AS lifetime_value,
    MAX(o.order_purchase_timestamp)    AS most_recent_order_at
FROM shopops_data.customers c
JOIN shopops_data.orders o ON o.customer_id = c.customer_id
LEFT JOIN shopops_data.order_payments p ON p.order_id = o.order_id
GROUP BY c.customer_unique_id;

-- seller ID, order count, late-rate aggregate, review aggregate
CREATE OR REPLACE VIEW vw_seller_metrics AS
SELECT
    oi.seller_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    AVG(
        CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
             THEN 1.0 ELSE 0.0 END
    ) AS late_delivery_rate,
    AVG(r.review_score) AS avg_review_score
FROM shopops_data.order_items oi
JOIN shopops_data.orders o ON o.order_id = oi.order_id
LEFT JOIN shopops_data.order_reviews r ON r.order_id = o.order_id
GROUP BY oi.seller_id;

-- order/delivery milestones and coarse geography (no precise location)
CREATE OR REPLACE VIEW vw_delivery_risk_inputs AS
SELECT
    o.order_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    c.customer_state
FROM shopops_data.orders o
JOIN shopops_data.customers c ON c.customer_id = o.customer_id;

-- order facts needed for a compensation proposal (no write path here)
CREATE OR REPLACE VIEW vw_compensation_eligibility AS
SELECT
    o.order_id,
    o.order_status,
    o.order_estimated_delivery_date,
    o.order_delivered_customer_date,
    (o.order_delivered_customer_date > o.order_estimated_delivery_date) AS is_late,
    SUM(p.payment_value) AS order_value
FROM shopops_data.orders o
LEFT JOIN shopops_data.order_payments p ON p.order_id = o.order_id
GROUP BY o.order_id, o.order_status, o.order_estimated_delivery_date,
         o.order_delivered_customer_date;
