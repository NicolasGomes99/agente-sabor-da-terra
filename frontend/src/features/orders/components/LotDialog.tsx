import { useEffect, useRef, useState } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { listProducers } from '../../registry/registryApi'
import type { Producer } from '../../registry/types'
import type { LotInput, LotRecord, OrderItemRecord, OrderRecord } from '../ordersApi'
import { LotForm } from './LotForm'

export interface LotDialogState {
  item: OrderItemRecord
  initial?: LotRecord
}

interface LotDialogProps {
  state: LotDialogState | null
  order: OrderRecord
  pending: boolean
  error: string | null
  onSubmit: (data: LotInput) => Promise<void>
  onCancel: () => void
}

type ProducersState =
  | { status: 'idle' | 'loading' | 'error' }
  | { status: 'ready'; producers: Producer[] }

export function LotDialog({
  state,
  order,
  pending,
  error,
  onSubmit,
  onCancel,
}: LotDialogProps) {
  const { logout } = useAuth()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [producers, setProducers] = useState<ProducersState>({
    status: 'idle',
  })

  const productId = state?.item.product_id ?? null

  const [loadedFor, setLoadedFor] = useState<string | null>(null)
  if (loadedFor !== productId) {
    setLoadedFor(productId)
    setProducers(productId === null ? { status: 'idle' } : { status: 'loading' })
  }

  useEffect(() => {
    if (state) dialogRef.current?.showModal()
    else dialogRef.current?.close()
  }, [state])

  useEffect(() => {
    if (productId === null) return

    const controller = new AbortController()

    listProducers(productId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setProducers({ status: 'ready', producers: result })
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        if (cause instanceof ApiError && cause.status === 401) {
          logout()
          return
        }
        setProducers({ status: 'error' })
      })

    return () => controller.abort()
  }, [productId, logout])

  return (
    <dialog
      className="order-dialog"
      ref={dialogRef}
      aria-labelledby="lot-dialog-heading"
      onCancel={(event) => {
        event.preventDefault()
        if (!pending) onCancel()
      }}
      onClose={onCancel}
    >
      <h2 id="lot-dialog-heading">
        {state?.initial ? 'Editar alocação' : 'Nova alocação'}
      </h2>

      {state && (
        <>
          {producers.status === 'loading' && (
            <p role="status">Carregando produtores…</p>
          )}

          {producers.status === 'error' && (
            <p className="order-error" role="alert">
              Não foi possível carregar os produtores deste produto.
            </p>
          )}

          {producers.status === 'ready' && (
            <LotForm
              order={order}
              item={state.item}
              initial={state.initial}
              producers={producers.producers}
              pending={pending}
              error={error}
              onSubmit={onSubmit}
              onCancel={onCancel}
            />
          )}
        </>
      )}
    </dialog>
  )
}
