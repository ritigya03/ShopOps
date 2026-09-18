# Approvals wiring — design

Status: approved by user
Date: 2026-09-18
Scope: backend (`GET /actions`) + third frontend sub-project (Approvals page).

## Backend: `GET /actions`

New endpoint, manager-only (`can_approve_compensation` — same gate as approve/reject). Optional `?status=` filter (`PROPOSED`, `SUCCEEDED`, `REJECTED`; omitted = all).

`action_requests` doesn't store the proposed amount or reason before approval (only `approved_amount`, populated *after* approval) — so each row is enriched by calling `calculate_compensation(order_id, policy_version)`, the same function `resolve_action` already calls for its freshness check. For a `SUCCEEDED` row, `proposed_amount` comes from the stored `approved_amount` (ground truth of what was actually approved); for everything else, from the fresh recomputation.

`app/schemas.py`:
```python
class ActionSummary(BaseModel):
    action_id: str
    order_id: str
    status: str
    requested_by: str
    approved_by: str | None
    policy_version: str
    expires_at: datetime | None
    is_expired: bool
    created_at: datetime
    proposed_amount: Decimal | None
    severity: str | None
    reason: str | None
```

`app/actions.py`: add `list_actions(status: str | None) -> list[ActionSummary]`.
`app/routes.py`: add `GET /actions`.

N+1 `calculate_compensation` calls per list request is fine at MVP queue sizes (a handful of pending proposals, not thousands) — same "correctness over premature optimization" call already made elsewhere in this codebase.

## Frontend: `ApprovalsPage`

- `lib/actions.ts`: `listActions(status?)` (GET, via `apiFetch`), `approveAction(id)` / `rejectAction(id)` (POST, via `apiFetch`).
- `ApprovalsPage` rewritten: real tabs (Pending/Approved/Rejected/Expired) computed from `status` + `is_expired`, fetched on tab switch. Approve/Reject buttons call the real endpoints and remove the card from the Pending list optimistically (real-time UI update), showing an inline error and restoring it if the call fails.
- Card shows: order id, amount, policy doc+version, reason, severity, expiry countdown for Pending; no actions for the other three tabs (just status).

## Testing

Backend: `tests/test_actions_list.py` (integration) — pending/approved/rejected filters return the right rows with real recomputed amounts; non-manager gets 403.
Frontend: manual, same pattern as the other sub-projects (no test infra yet).
