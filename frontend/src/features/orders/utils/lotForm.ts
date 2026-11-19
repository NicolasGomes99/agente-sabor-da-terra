import { validQuantity } from '../orderHelpers'
import type { LotInput } from '../ordersApi'

export const ALLOWED_UNITS = ['kg', 'g', 't', 'un'] as const

export function buildUnitOptions(
  itemUnit: string,
  initialUnit?: string | null,
): string[] {
  return Array.from(
    new Set(
      [itemUnit, initialUnit, ...ALLOWED_UNITS].filter(
        (value): value is string => Boolean(value),
      ),
    ),
  )
}

export interface LotFormValues {
  producerId: string
  quantity: string
  unit: string
  deliveryDate: string
  confirmed: boolean
}

export function validateLotForm(
  values: LotFormValues,
): { input?: LotInput; error?: string } {
  const { producerId, quantity, unit, deliveryDate, confirmed } = values

  if (!producerId) {
    return { error: 'Selecione o produtor que atenderá o item.' }
  }

  const normalized = quantity.trim().replace(',', '.')
  if (!validQuantity(normalized)) {
    return {
      error: 'Informe uma quantidade positiva com até 3 casas decimais.',
    }
  }

  if (!unit.trim()) {
    return { error: 'Informe a unidade da alocação.' }
  }

  if (!deliveryDate) {
    return { error: 'Informe a data prevista de entrega.' }
  }

  if (!confirmed) {
    return {
      error:
        'Confirme a disponibilidade do produtor para a quantidade, a '
        + 'unidade e a data informadas.',
    }
  }

  return {
    input: {
      producer_id: producerId,
      quantity: normalized,
      unit: unit.trim(),
      delivery_date: deliveryDate,
      availability_confirmed: confirmed,
    },
  }
}
