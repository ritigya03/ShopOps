# Dashboard wiring — design

Status: approved by user
Date: 2026-09-18
Scope: fourth and final frontend sub-project, plus one small backend addition (`GET /audit-events`). Dashboard home's aggregate stats/activity feed are explicitly out of scope (no backend support, not being added this pass).

## Orders page → ID lookup

No new backend endpoint (`GET /orders/{id}` already exists, all 3 roles can call it). Table replaced with a search box: type an order ID, submit, see the real `OrderTimeline` fields (status, purchase/estimated/delivered dates, order value, seller count) or a "not found" message. `lib/orders.ts`: `getOrder(orderId)`.

## Sellers page → ID lookup

Same pattern. `GET /sellers/{id}/metrics` already exists, `OperationsManager`-only (matches existing nav gating). `lib/sellers.ts`: `getSellerMetrics(sellerId)`.

## Audit Log — new backend endpoint

`GET /audit-events?limit=50` (default 50, most recent first). New permission `can_view_audit_log`, `OperationsManager`-only (matches existing nav gating — this role is the closest thing to an admin in the 3-role system).

`app/schemas.py`:
```python
class AuditEventSummary(BaseModel):
    event_id: str
    occurred_at: datetime
    user_id: str
    role_snapshot: str
    tool_name: str
    outcome: str
    policy_version: str | None
```

New `app/audit_log.py`: `list_audit_events(limit: int) -> list[AuditEventSummary]` (plain `SELECT ... ORDER BY occurred_at DESC LIMIT :limit` against `audit_events`, no cursor pagination — simple MVP list, matches the "correctness over premature complexity" calls made elsewhere in this codebase). `app/routes.py`: add the route. `lib/audit.ts` (frontend): `listAuditEvents()`.

## Testing

Backend: `tests/test_audit_events_list.py` (integration) — a known audit event (e.g. from calling `/orders/{id}`) shows up in the list; non-manager gets 403.
Frontend: manual, same as the other sub-projects.
