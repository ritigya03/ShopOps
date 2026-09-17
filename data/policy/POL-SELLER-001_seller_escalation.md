---
doc_id: POL-SELLER-001
version: "1.0"
title: Seller Performance and Escalation Policy
domain: seller
effective_from: 2026-01-01
status: active
---

## 1. Purpose

Defines the thresholds ShopOps uses to flag a seller for review when an
Operations Manager asks a seller-performance question, and the escalation
guidance `search_policy` returns alongside `get_seller_metrics` results.

## 2. Late-rate threshold

A seller's **late-delivery rate** is the share of their orders where
`order_delivered_customer_date` is later than
`order_estimated_delivery_date` (see POL-DELIVERY-001 §3), over a rolling
window of at most 365 days, per `get_seller_metrics`.

- **Below 5%**: no action.
- **5% to 10%**: flagged for quarterly review, no immediate action.
- **Above 10%**: flagged for escalation — recommend Operations Manager
  review within 30 days.

## 3. Review score threshold

A seller whose average `review_score` (from `order_reviews`) over the same
window falls below **3.0** is flagged for escalation regardless of
late-delivery rate.

## 4. Aggregate-only reporting

Seller performance answers must report cohort aggregates only. A cohort
below the minimum size threshold (10 orders in the window) must not be
reported individually — return "insufficient data" instead of a
metric that could single out a low-volume seller unfairly.

## 5. Escalation is a recommendation, not an action

Flags from §2-3 are advisory. This policy does not authorize suspending,
delisting, or penalizing a seller — that decision belongs to a human
Operations Manager, made outside this system.
