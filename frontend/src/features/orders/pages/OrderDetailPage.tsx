import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { deliveryLabel, orderError } from '../orderHelpers'
import { cancelOrder } from '../ordersApi'
import { useOrder } from '../useOrder'
import './orders.css'

function OrderDetail({ id }: { id: string }) {
  const { state, setState, retry } = useOrder(id)
  const { logout } = useAuth()
  const location = useLocation()
  const [confirming, setConfirming] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(location.state?.notice ?? null)
  const dialog = useRef<HTMLDialogElement>(null)
  const inProgress = useRef(false)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    if (confirming) dialog.current?.showModal()
    else dialog.current?.close()
  }, [confirming])

  async function confirmCancel() {
    if (inProgress.current) return
    inProgress.current = true
    setPending(true)
    setError(null)
    try {
      const order = await cancelOrder(id)
      if (!mounted.current) return
      setState({ status: 'ready', order })
      setNotice('Pedido cancelado. Os dados continuam disponíveis para consulta.')
      setConfirming(false)
    } catch (cause) {
      if (!mounted.current) return
      if (cause instanceof ApiError && cause.status === 401) logout()
      else setError(orderError(cause))
    } finally {
      inProgress.current = false
      if (mounted.current) setPending(false)
    }
  }

  if (state.status === 'loading') return <p role="status">Carregando pedido…</p>
  if (state.status === 'error') return <div className="order-panel">
    <h1>Detalhes do pedido</h1><p className="order-error" role="alert">{state.message}</p>
    <button className="order-button" onClick={retry}>Tentar novamente</button>
  </div>
  const { order } = state
  return <>
    <header className="orders-heading">
      <div><p className="order-eyebrow">PEDIDO #{order.id.slice(0, 8)}</p>
        <h1>{order.buyer}</h1>
        <span className={`order-badge ${order.cancelled ? 'is-cancelled' : ''}`}>{order.cancelled ? 'Cancelado' : 'Ativo'}</span>
      </div>
      {!order.cancelled && <div className="order-actions">
        <button className="order-button order-danger" onClick={() => {
          setError(null); setConfirming(true)
        }}>Cancelar pedido</button>
        <Link className="order-button order-primary" to={`/orders/${id}/edit`}>Editar pedido</Link>
      </div>}
    </header>
    {notice && <p className="order-notice" role="status">{notice}</p>}
    <div className="order-detail-grid">
      <section className="order-panel"><h2>Dados do pedido</h2>
        <dl className="order-data">
          <dt>Comprador</dt><dd>{order.buyer}</dd>
          <dt>Itens, quantidades e unidades</dt>
          <dd>{order.items.length > 0 ? <div className="order-table-scroll">
            <table className="order-table">
              <caption className="sr-only">Itens do pedido</caption>
              <thead><tr><th scope="col">Produto</th><th scope="col">Quantidade</th><th scope="col">Unidade</th></tr></thead>
              <tbody>{order.items.map((item) => <tr key={item.id}>
                <td>{item.product.name}</td><td>{item.quantity}</td><td>{item.unit}</td>
              </tr>)}</tbody>
            </table>
          </div> : <p className="order-notice">Itens pendentes de estruturação.</p>}</dd>
          {order.products && <><dt>Descrição original do pedido</dt>
            <dd className="order-multiline">{order.products}</dd></>}
          <dt>Condições de atendimento</dt><dd className="order-multiline">{order.conditions || 'Nenhuma condição informada.'}</dd>
        </dl>
      </section>
      <aside className="order-panel"><h2>Entrega</h2>
        <p className="order-delivery">{deliveryLabel(order)}</p>
        <p className="order-muted">{order.delivery_end_date ? 'Período de entrega informado.' : 'Entrega em uma única data.'}</p>
        <hr /><p className="order-muted">Identificador do pedido</p>
        <p className="order-id">{order.id}</p>
        {order.cancelled && <p className="order-muted">Pedido cancelado. A edição está indisponível.</p>}
      </aside>
    </div>
    <dialog className="order-dialog" ref={dialog} aria-labelledby="cancel-heading"
      onCancel={(event) => { event.preventDefault(); if (!pending) setConfirming(false) }}
      onClose={() => setConfirming(false)}>
      <h2 id="cancel-heading">Cancelar este pedido?</h2>
      <p>O pedido de <strong>{order.buyer}</strong> será marcado como cancelado e não poderá ser editado. Os dados continuarão disponíveis para consulta.</p>
      {error && <p className="order-error" role="alert">{error}</p>}
      <div className="order-actions">
        <button className="order-button" disabled={pending} autoFocus onClick={() => setConfirming(false)}>Manter pedido</button>
        <button className="order-button order-danger" disabled={pending} onClick={() => void confirmCancel()}>
          {pending ? 'Cancelando…' : 'Confirmar cancelamento'}</button>
      </div>
    </dialog>
  </>
}

export function OrderDetailPage() {
  const { orderId = '' } = useParams()
  return <AppShell><section className="orders-page">
    <Link className="order-back" to="/orders">← Pedidos</Link>
    <OrderDetail key={orderId} id={orderId} />
  </section></AppShell>
}
