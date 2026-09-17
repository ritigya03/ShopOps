---
doc_id: POL-COMP-001
version: "1.0"
title: Compensation and Refund Eligibility Policy
domain: policy
effective_from: 2026-01-01
status: active
---

## 1. Purpose

Defines when a compensation or refund proposal may be generated, and at
what amount, for `calculate_compensation`. This policy produces a
**non-binding proposal only** — no proposal under this policy authorizes
payment. Payment requires a separate signed manager approval, per the
approval workflow in the Technical Design Document §8.

## 2. Eligibility conditions

An order is eligible for a compensation proposal only if **all** of the
following hold:

1. `order_status` is `delivered` (undelivered orders are handled under
   POL-DELIVERY-001 as at-risk, not compensated).
2. The order is late under POL-DELIVERY-001 §3.
3. No prior `action_requests` entry exists for this order with status
   `APPROVED` or `SUCCEEDED` (an order may not be compensated twice).

If any condition fails, the agent must state the failing condition rather
than propose a partial or approximate compensation.

## 3. Compensation tiers

Compensation is calculated as a percentage of the order's total
`payment_value`, based on the delay severity band from POL-DELIVERY-001
§4:

| Delay severity | Compensation |
|---|---|
| Minor delay (1-3 days) | 10% of order value |
| Moderate delay (4-7 days) | 25% of order value |
| Severe delay (>7 days) | 50% of order value, capped at 150 (local currency units) |

## 4. Approval thresholds

- Proposals under 50 currency units: may be approved by a **Support
  Agent's manager** at Operations Manager role.
- Proposals of 50 or more: require Operations Manager approval **and**
  must cite this policy's version and section in the approval record.
- No proposal may be auto-approved. Every proposal enters `action_requests`
  with status `PROPOSED` and waits for human approval regardless of
  amount.

## 5. Idempotency

A single order may have at most one active (`PROPOSED` or `APPROVED`)
compensation request at a time. A repeated request for the same order
while one is pending returns the existing request rather than creating a
duplicate.
