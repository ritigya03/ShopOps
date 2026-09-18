import { apiFetch } from './api'

export interface AuditEventSummary {
  event_id: string
  occurred_at: string
  user_id: string
  role_snapshot: string
  tool_name: string
  outcome: string
  policy_version: string | null
}

export async function listAuditEvents(): Promise<AuditEventSummary[]> {
  const resp = await apiFetch('/audit-events')
  if (!resp.ok) throw new Error(`Failed to load audit events (${resp.status})`)
  return resp.json()
}
