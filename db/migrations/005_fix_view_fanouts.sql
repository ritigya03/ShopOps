-- Fixes order_items x order_payments/order_reviews fan-out inflation in
-- vw_order_ops and vw_seller_metrics (found by final whole-branch review,
-- 2026-09-18). Both views joined order_items directly against per-order
-- payment/review data with no de-duplication, so an order/seller with N
-- items counted each payment or review N times.
SET search_path TO shopops_views;

CREATE OR REPLACE VIEW vw_order_ops AS
WITH order_totals AS (
    SELECT order_id, SUM(payment_value) AS order_value
    FROM shopops_data.order_payments
    GROUP BY order_id
),
order_sellers AS (
    SELECT DISTINCT order_id, seller_id FROM shopops_data.order_items
)
SELECT
    o.order_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_estimated_delivery_date,
    o.order_delivered_customer_date,
    os.seller_id,
    ot.order_value
FROM shopops_data.orders o
JOIN order_sellers os USING (order_id)
LEFT JOIN order_totals ot USING (order_id);

CREATE OR REPLACE VIEW vw_seller_metrics AS
WITH seller_orders AS (
    SELECT DISTINCT seller_id, order_id FROM shopops_data.order_items
),
order_reviews_avg AS (
    SELECT order_id, AVG(review_score) AS review_score
    FROM shopops_data.order_reviews
    GROUP BY order_id
)
SELECT
    so.seller_id,
    COUNT(DISTINCT so.order_id) AS order_count,
    AVG(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
             THEN 1.0 ELSE 0.0 END) AS late_delivery_rate,
    AVG(ora.review_score) AS avg_review_score
FROM seller_orders so
JOIN shopops_data.orders o ON o.order_id = so.order_id
LEFT JOIN order_reviews_avg ora ON ora.order_id = so.order_id
GROUP BY so.seller_id;
