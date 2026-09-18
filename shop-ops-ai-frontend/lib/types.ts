// Mirrors app/schemas.py's Pydantic models - field names match the JSON
// the backend actually returns (snake_case, Decimal fields as strings).

export interface PolicyEvidence {
  doc_id: string
  version: string
  section: string
  excerpt: string
  score: number
}

export interface CompensationProposal {
  order_id: string
  eligible: boolean
  reason: string
  policy_doc_id: string
  policy_version: string
  severity: string | null
  compensation_percentage: number | null
  order_value: string | null
  proposed_amount: string | null
  cap_applied: boolean
}
