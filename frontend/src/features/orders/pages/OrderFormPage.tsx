import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { OrderForm } from '../components/OrderForm'
import { orderError } from '../orderHelpers'
import {
  createOrder,
  updateOrder,
  type OrderRecord,
  type OrderUpdate,
} from '../ordersApi'
import { useOrder } from '../useOrder'
import './orders.css'

function FormContent({ order }: { order?: OrderRecord }) {
  const navigate = useNavigate()
  const { logout } = useAuth()

  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(payload: OrderUpdate) {
    setPending(true)
    setError(null)

    try {
      const saved = order
        ? await updateOrder(order.id, payload)
        : await createOrder({
            ...payload,
            items: payload.items.map(
              ({ product_id, quantity, unit }) => ({
                product_id,
                quantity,
                unit,
              }),
            ),
          })

      navigate(`/orders/${saved.id}`, {
        replace: true,
        state: {
          notice: order
            ? 'Pedido atualizado.'
            : 'Pedido cadastrado.',
        },
      })
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        logout()
      } else {
        setError(orderError(cause))
      }
    } finally {
      setPending(false)
    }
  }

  if (order?.cancelled) {
    return (
      <div className="order-panel">
        <p role="alert">
          Este pedido foi cancelado e não pode ser editado.
        </p>
        <Link to={`/orders/${order.id}`}>
          Consultar pedido
        </Link>
      </div>
    )
  }

  return (
    <OrderForm
      initial={order}
      pending={pending}
      error={error}
      onSubmit={save}
      backTo={order ? `/orders/${order.id}` : '/orders'}
    />
  )
}

function EditContent({ id }: { id: string }) {
  const { state, retry } = useOrder(id)

  if (state.status === 'loading') {
    return <p role="status">Carregando pedido…</p>
  }

  if (state.status === 'error') {
    return (
      <div className="order-panel">
        <p className="order-error" role="alert">
          {state.message}
        </p>
        <button
          className="order-button"
          type="button"
          onClick={retry}
        >
          Tentar novamente
        </button>
      </div>
    )
  }

  return (
    <FormContent
      key={state.order.id}
      order={state.order}
    />
  )
}

export function OrderFormPage() {
  const { orderId } = useParams()

  return (
    <AppShell>
      <section className="orders-page">
        <Link className="order-back" to="/orders">
          ← Pedidos
        </Link>

        <header className="orders-heading">
          <div>
            <p className="order-eyebrow">GESTÃO DE PEDIDOS</p>
            <h1>{orderId ? 'Editar pedido' : 'Novo pedido'}</h1>
            <p className="order-muted">
              Registre o comprador, os itens e o prazo de entrega.
            </p>
          </div>
        </header>

        {orderId ? (
          <EditContent key={orderId} id={orderId} />
        ) : (
          <FormContent />
        )}
      </section>
    </AppShell>
  )
}