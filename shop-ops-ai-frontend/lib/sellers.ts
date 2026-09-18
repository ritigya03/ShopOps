import { apiFetch } from './api'

export interface SellerMetricsResult {
  seller_id: string
  order_count: number
  late_delivery_rate: number
  avg_review_score: number | null
}

export async function getSellerMetrics(sellerId: string): Promise<SellerMetricsResult | null> {
  const resp = await apiFetch(`/sellers/${encodeURIComponent(sellerId)}/metrics`)
  if (resp.status === 404) return null
  if (!resp.ok) throw new Error(`Failed to load seller (${resp.status})`)
  return resp.json()
}
