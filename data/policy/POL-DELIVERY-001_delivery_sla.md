---
doc_id: POL-DELIVERY-001
version: "1.0"
title: Delivery SLA and Delay Definition Policy
domain: shipping
effective_from: 2026-01-01
status: active
---

## 1. Purpose

Defines what counts as a "late" or "at-risk" order and the delivery
milestones ShopOps agents use to answer delivery-status and delay
questions. This policy is the basis for `estimate_delivery_risk` and the
delay facts surfaced by `get_order`.

## 2. Delivery milestones

Every order has four tracked timestamps: purchase, carrier handoff,
customer delivery, and estimated delivery. An order is only evaluated
against this policy once `order_purchase_timestamp` is recorded.

## 3. Late delivery definition

An order is **late** when `order_delivered_customer_date` is later than
`order_estimated_delivery_date`. An order still in transit is **at risk**
when the current date is later than `order_estimated_delivery_date` and no
`order_delivered_customer_date` is recorded yet.

## 4. Delay severity bands

- **Minor delay**: delivered 1-3 days after the estimate.
- **Moderate delay**: delivered 4-7 days after the estimate.
- **Severe delay**: delivered more than 7 days after the estimate, or an
  order still undelivered more than 7 days past the estimate.

Severity band determines the compensation tier in
POL-COMP-001 §3.

## 5. External signal handling

Shipping, weather, or geolocation signals are **advisory only**. If such a
signal is unavailable, the agent must say so explicitly rather than
inferring a cause for the delay. The delay determination in §3 relies only
on the order's own recorded timestamps, never on external signals.

## 6. Non-attribution

This policy does not assign fault (carrier, seller, or customer-side) for
a delay. Fault attribution is out of scope for the MVP and requires human
review.
