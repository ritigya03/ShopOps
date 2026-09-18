import { apiFetch } from './api'

export interface ActionSummary {
  action_id: string
  order_id: string
  status: string
  requested_by: string
  approved_by: string | null
  policy_version: string
  expires_at: string | null
  is_expired: boolean
  created_at: string
  proposed_amount: string | null
  severity: string | null
  reason: string | null
}

async function throwIfNotOk(resp: Response, fallback: string): Promise<void> {
  if (resp.ok) return
  const body = await resp.json().catch(() => ({}))
  throw new Error(body.detail ?? fallback)
}

export async function listActions(status: string): Promise<ActionSummary[]> {
  const resp = await apiFetch(`/actions?status=${encodeURIComponent(status)}`)
  await throwIfNotOk(resp, `Failed to load actions (${resp.status})`)
  return resp.json()
}

export async function approveAction(actionId: string): Promise<void> {
  const resp = await apiFetch(`/actions/${actionId}/approve`, { method: 'POST' })
  await throwIfNotOk(resp, `Approve failed (${resp.status})`)
}

export async function rejectAction(actionId: string): Promise<void> {
  const resp = await apiFetch(`/actions/${actionId}/reject`, { method: 'POST' })
  await throwIfNotOk(resp, `Reject failed (${resp.status})`)
}
