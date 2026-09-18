import { apiFetch } from './api'

export interface OrderTimelineResult {
  order_id: string
  order_status: string
  purchase_timestamp: string
  estimated_delivery_date: string
  delivered_customer_date: string | null
  order_value: string
  seller_count: number
}

export async function getOrder(orderId: string): Promise<OrderTimelineResult | null> {
  const resp = await apiFetch(`/orders/${encodeURIComponent(orderId)}`)
  if (resp.status === 404) return null
  if (!resp.ok) throw new Error(`Failed to load order (${resp.status})`)
  return resp.json()
}
