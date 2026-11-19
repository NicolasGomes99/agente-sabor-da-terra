import { useState } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import {
  createLot,
  deleteLot,
  updateLot,
  type LotInput,
  type LotRecord,
  type OrderItemRecord,
  type OrderRecord,
} from '../ordersApi'
import { LotDialog, type LotDialogState } from './LotDialog'
import { LotItemPanel } from './LotItemPanel'

interface LotSectionProps {
  order: OrderRecord
  onChanged: () => Promise<void> | void
}

function saveErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 422) {
    return 'Não foi possível salvar a alocação. Confira o produtor, a '
      + 'quantidade, a unidade e a data dentro do prazo do pedido.'
  }
  return 'Não foi possível salvar a alocação. Tente novamente.'
}

export function LotSection({ order, onChanged }: LotSectionProps) {
  const { logout } = useAuth()
  const [dialog, setDialog] = useState<LotDialogState | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  function openCreate(item: OrderItemRecord) {
    setError(null)
    setDialog({ item })
  }

  function openEdit(item: OrderItemRecord, lot: LotRecord) {
    setError(null)
    setDialog({ item, initial: lot })
  }

  function closeDialog() {
    setDialog(null)
    setError(null)
  }

  async function submit(payload: LotInput) {
    if (!dialog) return
    setPending(true)
    setError(null)

    try {
      if (dialog.initial) {
        await updateLot(dialog.initial.id, payload)
      } else {
        await createLot(order.id, dialog.item.id, payload)
      }
      closeDialog()
      await onChanged()
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        logout()
        return
      }
      setError(saveErrorMessage(cause))
    } finally {
      setPending(false)
    }
  }

  async function remove(lot: LotRecord) {
    if (deletingId) return
    setDeletingId(lot.id)
    setError(null)

    try {
      await deleteLot(lot.id)
      await onChanged()
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        logout()
        return
      }
      setError('Não foi possível excluir a alocação. Tente novamente.')
    } finally {
      setDeletingId(null)
    }
  }

  const items = order.items ?? []

  return (
    <section className="order-panel order-lots" aria-labelledby="lots-heading">
      <h2 id="lots-heading">Alocações por item</h2>

      {items.length === 0 && (
        <p className="order-muted">
          Este pedido ainda não tem itens estruturados para alocar.
        </p>
      )}

      {error && (
        <p className="order-error" role="alert">
          {error}
        </p>
      )}

      {items.map((item) => (
        <LotItemPanel
          key={item.id}
          order={order}
          item={item}
          deletingId={deletingId}
          onCreate={openCreate}
          onEdit={openEdit}
          onDelete={remove}
        />
      ))}

      <LotDialog
        state={dialog}
        order={order}
        pending={pending}
        error={error}
        onSubmit={submit}
        onCancel={closeDialog}
      />
    </section>
  )
}
