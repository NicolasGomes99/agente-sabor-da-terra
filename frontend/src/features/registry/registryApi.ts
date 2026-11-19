import { apiRequest } from '../../lib/api-client'

import type { Producer, Product } from './types'

export function listProducts(signal?: AbortSignal): Promise<Product[]> {
  return apiRequest<Product[]>('/products', { signal })
}

export function listProducers(
  productId?: string,
  signal?: AbortSignal,
): Promise<Producer[]> {
  const path = productId === undefined
    ? '/producers'
    : `/producers?${new URLSearchParams({ product_id: productId })}`

  return apiRequest<Producer[]>(path, { signal })
}

export function getProducer(id: string, signal?: AbortSignal): Promise<Producer> {
  return apiRequest<Producer>(`/producers/${encodeURIComponent(id)}`, { signal })
}
