import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import {
  deliveryLabel,
  itemsLabel,
  orderError,
} from '../orderHelpers'
import { listOrders, type OrderRecord } from '../ordersApi'
import './orders.css'

type ListState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; orders: OrderRecord[] }

export function OrdersPage() {
  const { logout } = useAuth()
  const [state, setState] = useState<ListState>({
    status: 'loading',
  })
  const [attempt, setAttempt] = useState(0)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    const controller = new AbortController()

    void listOrders(controller.signal)
      .then((orders) => {
        if (!controller.signal.aborted) {
          setState({ status: 'ready', orders })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return

        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }

        setState({
          status: 'error',
          message: orderError(error),
        })
      })

    return () => controller.abort()
  }, [attempt, logout])

  function retry() {
    setState({ status: 'loading' })
    setAttempt((value) => value + 1)
  }

  const orders = state.status === 'ready' ? state.orders : []

  const visible = orders.filter((order) => {
    const matchesStatus =
      filter === 'all' ||
      (filter === 'cancelled' ? order.cancelled : !order.cancelled)

    const searchable =
      `${order.buyer} ${itemsLabel(order)} ${order.id}`
        .toLocaleLowerCase('pt-BR')

    const matchesSearch = searchable.includes(
      query.trim().toLocaleLowerCase('pt-BR'),
    )

    return matchesStatus && matchesSearch
  })

  return (
    <AppShell>
      <section
        className="orders-page"
        aria-labelledby="orders-heading"
      >
        <header className="orders-heading">
          <div>
            <p className="order-eyebrow">
              OPERAÇÃO DA COOPERATIVA
            </p>
            <h1 id="orders-heading">Pedidos</h1>
            <p className="order-muted">
              Acompanhe os pedidos e organize as próximas entregas.
            </p>
          </div>

          <Link
            className="order-button order-primary"
            to="/orders/new"
          >
            + Novo pedido
          </Link>
        </header>

        {state.status === 'loading' && (
          <p className="order-panel" role="status">
            Carregando pedidos…
          </p>
        )}

        {state.status === 'error' && (
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
        )}

        {state.status === 'ready' && (
          <>
            <div
              className="order-summary"
              aria-label="Resumo de pedidos"
            >
              <div>
                <span>Total de pedidos</span>
                <strong>{orders.length}</strong>
              </div>
              <div>
                <span>Ativos</span>
                <strong>
                  {orders.filter((order) => !order.cancelled).length}
                </strong>
              </div>
              <div>
                <span>Cancelados</span>
                <strong>
                  {orders.filter((order) => order.cancelled).length}
                </strong>
              </div>
            </div>

            <div className="order-panel order-list-panel">
              <div className="order-filters">
                <div>
                  <label htmlFor="order-search">
                    Buscar pedido
                  </label>
                  <input
                    id="order-search"
                    type="search"
                    value={query}
                    placeholder="Comprador, produto ou ID"
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </div>

                <div>
                  <label htmlFor="order-status">Status</label>
                  <select
                    id="order-status"
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                  >
                    <option value="all">Todos</option>
                    <option value="active">Ativos</option>
                    <option value="cancelled">Cancelados</option>
                  </select>
                </div>
              </div>

              {orders.length === 0 ? (
                <div className="order-empty">
                  <h2>Seu primeiro pedido começa aqui</h2>
                  <p className="order-muted">
                    Cadastre um comprador, os itens e a data de entrega.
                  </p>
                  <Link
                    className="order-button order-primary"
                    to="/orders/new"
                  >
                    Cadastrar pedido
                  </Link>
                </div>
              ) : visible.length === 0 ? (
                <p className="order-empty" role="status">
                  Nenhum pedido encontrado para estes filtros.
                </p>
              ) : (
                <div className="order-table-scroll">
                  <table className="order-table">
                    <caption className="sr-only">
                      Pedidos cadastrados
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Comprador / pedido</th>
                        <th scope="col">Itens</th>
                        <th scope="col">Entrega</th>
                        <th scope="col">Status</th>
                        <th scope="col">Ações</th>
                      </tr>
                    </thead>

                    <tbody>
                      {visible.map((order) => (
                        <tr key={order.id}>
                          <td>
                            <Link
                              className="order-buyer"
                              to={`/orders/${order.id}`}
                            >
                              {order.buyer}
                            </Link>
                            <small>#{order.id.slice(0, 8)}</small>
                          </td>

                          <td>
                            <span className="order-item-preview">
                              {itemsLabel(order)}
                            </span>
                            {order.needs_item_structuring && (
                              <small>
                                Itens pendentes de estruturação
                              </small>
                            )}
                          </td>

                          <td>{deliveryLabel(order)}</td>

                          <td>
                            <span
                              className={`order-badge ${
                                order.cancelled ? 'is-cancelled' : ''
                              }`}
                            >
                              {order.cancelled ? 'Cancelado' : 'Ativo'}
                            </span>
                          </td>

                          <td>
                            <Link
                              className="order-text-link"
                              to={`/orders/${order.id}`}
                              aria-label={`Ver pedido de ${order.buyer}`}
                            >
                              Ver detalhes →
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <p className="order-list-count" role="status">
                {visible.length} de {orders.length} pedidos
              </p>
            </div>
          </>
        )}
      </section>
    </AppShell>
  )
}