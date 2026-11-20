import { ApiError } from '../../lib/api-client'
import type { OrderRecord } from './ordersApi'

export function formatDate(value: string): string {
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

export function deliveryLabel(order: OrderRecord): string {
  const start = formatDate(order.delivery_start_date)

  if (
    order.delivery_end_date &&
    order.delivery_end_date !== order.delivery_start_date
  ) {
    return `${start} a ${formatDate(order.delivery_end_date)}`
  }

  return start
}

export function isOrderVersionConflict(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) return false
  const details = error.details
  if (typeof details !== 'object' || details === null || !('detail' in details)) return false
  const detail = details.detail
  return typeof detail === 'object' && detail !== null &&
    'code' in detail && detail.code === 'order_version_conflict'
}

export function apiErrorDetail(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null
  const details = error.details
  if (typeof details !== 'object' || details === null || !('detail' in details)) return null
  const detail = details.detail
  return typeof detail === 'string' && detail.trim() ? detail : null
}

export function orderError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return 'Pedido não encontrado. Ele pode estar indisponível.'
    }

    if (isOrderVersionConflict(error)) {
      return 'Este pedido foi alterado por outra operação. Suas alterações ainda não foram salvas. Recarregue o pedido e revise os dados antes de tentar novamente.'
    }

    const detail = apiErrorDetail(error)
    if (detail) {
      return detail
    }

    if (error.status === 409) {
      return 'Este pedido foi cancelado e não pode ser editado.'
    }

    if (error.status === 422) {
      return 'Confira os produtos, as quantidades, as unidades e o período de entrega antes de tentar novamente.'
    }
  }

  return 'Não foi possível concluir a operação. Verifique sua conexão e tente novamente.'
}

export function itemsLabel(order: OrderRecord): string {
  if (order.items.length > 0) {
    return order.items
      .map(
        (item) =>
          `${item.product.name}: ${item.quantity} ${item.unit}`,
      )
      .join(' · ')
  }

  return order.products || 'Itens pendentes de estruturação'
}

export function validQuantity(value: string): boolean {
  return (
    /^\d{1,15}(?:\.\d{1,3})?$/.test(value) &&
    /[1-9]/.test(value)
  )
}

export function balanceLabel(balance: string | null | undefined): string {
  if (balance === null || balance === undefined) return 'Indeterminado'
  return balance
}

export function availabilityLabel(confirmed: boolean | null): string {
  return confirmed ? 'Confirmada' : 'Pendente'
}