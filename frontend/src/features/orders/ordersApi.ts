import { apiRequest } from '../../lib/api-client'
import type { Product } from '../registry/types'

export interface OrderItemInput {
  product_id: string
  quantity: string
  unit: string
}

export interface OrderItemUpdate extends OrderItemInput {
  id?: string
}

export interface LotRecord {
  id: string
  item_id: string | null
  producer: { id: string; name: string }
  quantity: string
  unit: string | null
  delivery_date: string
  availability_confirmed: boolean | null
}

export interface LotInput {
  producer_id: string
  quantity: string
  unit: string
  delivery_date: string
  availability_confirmed: boolean
}

export interface OrderItemRecord extends OrderItemInput {
  id: string
  product: Product
  lots?: LotRecord[]
  balance?: string | null
}

export interface OrderInput {
  buyer: string
  conditions: string
  delivery_start_date: string
  delivery_end_date: string | null
  items: OrderItemInput[]
}

export interface OrderFormData extends Omit<OrderInput, 'items'> {
  items: OrderItemUpdate[]
}

export interface OrderUpdate extends OrderFormData {
  version: number
}

export interface OrderRecord extends Omit<OrderInput, 'items'> {
  id: string
  version: number
  session_id: string | null
  cancelled: boolean
  products: string
  needs_item_structuring: boolean
  items: OrderItemRecord[]
}

export function listOrders(
  signal?: AbortSignal,
): Promise<OrderRecord[]> {
  return apiRequest('/orders', { signal })
}

export function getOrder(
  id: string,
  signal?: AbortSignal,
): Promise<OrderRecord> {
  return apiRequest(`/orders/${encodeURIComponent(id)}`, {
    signal,
  })
}

export function createOrder(
  payload: OrderInput,
): Promise<OrderRecord> {
  return apiRequest('/orders', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateOrder(
  id: string,
  payload: OrderUpdate,
): Promise<OrderRecord> {
  return apiRequest(`/orders/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function cancelOrder(id: string): Promise<OrderRecord> {
  return apiRequest(`/orders/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
  })
}

export function createLot(
  orderId: string,
  itemId: string,
  payload: LotInput,
): Promise<LotRecord> {
  return apiRequest(
    `/orders/${encodeURIComponent(orderId)}/items/${encodeURIComponent(itemId)}/lots`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export function updateLot(
  lotId: string,
  payload: LotInput,
): Promise<LotRecord> {
  return apiRequest(`/lots/${encodeURIComponent(lotId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteLot(lotId: string): Promise<void> {
  return apiRequest(`/lots/${encodeURIComponent(lotId)}`, {
    method: 'DELETE',
  })
}