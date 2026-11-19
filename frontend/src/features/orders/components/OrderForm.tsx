import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { listProducts } from '../../registry/registryApi'
import type { Product } from '../../registry/types'
import { validQuantity } from '../orderHelpers'
import type { OrderRecord, OrderFormData } from '../ordersApi'

interface OrderFormProps {
  initial?: OrderRecord
  pending: boolean
  conflict?: boolean
  error: string | null
  onSubmit: (data: OrderFormData) => Promise<void>
  backTo: string
}

interface ItemRow {
  key: string
  id?: string
  product_id: string
  quantity: string
  unit: string
}

type CatalogState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; products: Product[] }

function emptyRow(key: string): ItemRow {
  return {
    key,
    product_id: '',
    quantity: '',
    unit: '',
  }
}

export function OrderForm({
  initial,
  pending,
  conflict = false,
  error,
  onSubmit,
  backTo,
}: OrderFormProps) {
  const { logout } = useAuth()

  const [buyer, setBuyer] = useState(initial?.buyer ?? '')
  const [conditions, setConditions] = useState(
    initial?.conditions ?? '',
  )
  const [start, setStart] = useState(
    initial?.delivery_start_date ?? '',
  )
  const [end, setEnd] = useState(
    initial?.delivery_end_date ?? '',
  )
  const [interval, setInterval] = useState(
    Boolean(initial?.delivery_end_date),
  )
  const [validation, setValidation] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<CatalogState>({
    status: 'loading',
  })
  const [attempt, setAttempt] = useState(0)

  const [items, setItems] = useState<ItemRow[]>(() =>
    initial?.items.length
      ? initial.items.map((item) => ({
          key: item.id,
          id: item.id,
          product_id: item.product_id,
          quantity: String(item.quantity),
          unit: item.unit,
        }))
      : [emptyRow('new-0')],
  )

  const nextKey = useRef(1)
  const submitting = useRef(false)

  useEffect(() => {
    const controller = new AbortController()

    void listProducts(controller.signal)
      .then((products) => {
        if (!controller.signal.aborted) {
          setCatalog({ status: 'ready', products })
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return

        if (cause instanceof ApiError && cause.status === 401) {
          logout()
          return
        }

        setCatalog({ status: 'error' })
      })

    return () => controller.abort()
  }, [attempt, logout])

  const products =
    catalog.status === 'ready' ? catalog.products : []

  const available =
    catalog.status === 'ready' && products.length > 0

  function changeItem(
    key: string,
    field: 'product_id' | 'quantity' | 'unit',
    value: string,
  ) {
    setItems((rows) =>
      rows.map((row) =>
        row.key === key ? { ...row, [field]: value } : row,
      ),
    )
  }

  function addItem() {
    const key = `new-${nextKey.current++}`
    setItems((rows) => [...rows, emptyRow(key)])
  }

  function retryCatalog() {
    setCatalog({ status: 'loading' })
    setAttempt((value) => value + 1)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (pending || conflict || submitting.current) return

    if (!available) {
      setValidation(
        'Aguarde o carregamento de um catálogo com produtos antes de salvar.',
      )
      return
    }

    if (!buyer.trim() || !start || (interval && !end)) {
      setValidation('Preencha o comprador e o prazo de entrega.')
      return
    }

    if (interval && end < start) {
      setValidation(
        'A data final deve ser igual ou posterior à data inicial.',
      )
      return
    }

    const invalidItems =
      items.length === 0 ||
      items.some(
        (item) =>
          !products.some(
            (product) => product.id === item.product_id,
          ) ||
          !validQuantity(item.quantity.trim().replace(',', '.')) ||
          !item.unit.trim(),
      )

    if (invalidItems) {
      setValidation(
        'Informe pelo menos um item com produto do catálogo, quantidade positiva (até 3 casas decimais) e unidade. A quantidade aceita até 15 dígitos inteiros.',
      )
      return
    }

    setValidation(null)
    submitting.current = true

    try {
      await onSubmit({
        buyer: buyer.trim(),
        conditions: conditions.trim(),
        delivery_start_date: start,
        delivery_end_date: interval ? end : null,
        items: items.map((item) => ({
          ...(item.id ? { id: item.id } : {}),
          product_id: item.product_id,
          quantity: item.quantity.trim().replace(',', '.'),
          unit: item.unit.trim(),
        })),
      })
    } finally {
      submitting.current = false
    }
  }

  return (
    <form
      className="order-form order-panel"
      onSubmit={submit}
      aria-busy={pending}
    >
      {initial?.needs_item_structuring && (
        <p className="order-notice">
          Este pedido ainda não tem itens estruturados.
          Selecione os produtos abaixo para organizá-lo.
        </p>
      )}

      {initial?.products && (
        <section
          className="order-legacy"
          aria-labelledby="legacy-heading"
        >
          <h2 id="legacy-heading">
            Descrição original do pedido
          </h2>
          <p className="order-multiline">{initial.products}</p>
          <p className="order-muted">
            Esta descrição será preservada ao salvar.
          </p>
        </section>
      )}

      <fieldset disabled={pending}>
        <legend>Dados do pedido</legend>

        <label htmlFor="order-buyer">
          Comprador <span aria-hidden="true">*</span>
        </label>
        <input
          id="order-buyer"
          required
          autoComplete="organization"
          value={buyer}
          onChange={(event) => setBuyer(event.target.value)}
        />

        <label htmlFor="order-conditions">
          Condições de atendimento
        </label>
        <textarea
          id="order-conditions"
          rows={3}
          value={conditions}
          onChange={(event) => setConditions(event.target.value)}
        />
      </fieldset>

      <fieldset
        disabled={pending}
        aria-describedby="order-items-help"
      >
        <legend>Itens do pedido</legend>

        <p id="order-items-help" className="order-muted">
          Adicione pelo menos um produto com sua quantidade e unidade.
        </p>

        {catalog.status === 'loading' && (
          <p role="status">Carregando catálogo de produtos…</p>
        )}

        {catalog.status === 'error' && (
          <div className="order-error" role="alert">
            <p>Não foi possível carregar o catálogo de produtos.</p>
            <button
              className="order-button"
              type="button"
              onClick={retryCatalog}
            >
              Recarregar catálogo
            </button>
          </div>
        )}

        {catalog.status === 'ready' && products.length === 0 && (
          <p className="order-notice" role="status">
            Nenhum produto cadastrado. É necessário ter produtos
            no catálogo para salvar pedidos.
          </p>
        )}

        {items.map((item, index) => (
          <div className="order-item-row" key={item.key}>
            <div>
              <label htmlFor={`product-${item.key}`}>
                Produto {index + 1} *
              </label>
              <select
                id={`product-${item.key}`}
                required
                disabled={!available}
                value={item.product_id}
                onChange={(event) =>
                  changeItem(
                    item.key,
                    'product_id',
                    event.target.value,
                  )
                }
              >
                <option value="">Selecione um produto</option>

                {item.product_id &&
                  !products.some(
                    (product) => product.id === item.product_id,
                  ) && (
                    <option value={item.product_id} disabled>
                      Produto indisponível — selecione outro
                    </option>
                  )}

                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor={`quantity-${item.key}`}>
                Quantidade {index + 1} *
              </label>
              <input
                id={`quantity-${item.key}`}
                required
                inputMode="decimal"
                placeholder="Ex.: 10,500"
                value={item.quantity}
                onChange={(event) =>
                  changeItem(
                    item.key,
                    'quantity',
                    event.target.value,
                  )
                }
              />
            </div>

            <div>
              <label htmlFor={`unit-${item.key}`}>
                Unidade {index + 1} *
              </label>
              <input
                id={`unit-${item.key}`}
                required
                placeholder="kg, un, caixa…"
                value={item.unit}
                onChange={(event) =>
                  changeItem(item.key, 'unit', event.target.value)
                }
              />
            </div>

            <button
              className="order-button order-danger"
              type="button"
              aria-label={`Remover item ${index + 1}`}
              disabled={items.length === 1}
              onClick={() =>
                setItems((rows) =>
                  rows.filter((row) => row.key !== item.key),
                )
              }
            >
              Remover
            </button>
          </div>
        ))}

        <button
          className="order-button"
          type="button"
          disabled={!available}
          onClick={addItem}
        >
          + Adicionar item
        </button>
      </fieldset>

      <fieldset disabled={pending}>
        <legend>Prazo de entrega</legend>

        <label className="order-checkbox">
          <input
            type="checkbox"
            checked={interval}
            onChange={(event) => setInterval(event.target.checked)}
          />
          Entrega em um intervalo de datas
        </label>

        <div className="order-date-grid">
          <div>
            <label htmlFor="order-start">
              {interval ? 'Data inicial' : 'Data de entrega'} *
            </label>
            <input
              id="order-start"
              type="date"
              required
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
          </div>

          {interval && (
            <div>
              <label htmlFor="order-end">Data final *</label>
              <input
                id="order-end"
                type="date"
                required
                min={start || undefined}
                value={end}
                onChange={(event) => setEnd(event.target.value)}
              />
            </div>
          )}
        </div>
      </fieldset>

      {(validation || error) && (
        <p className="order-error" role="alert">
          {validation || error}
        </p>
      )}

      <div className="order-form-footer">
        <span className="order-muted">* Campos obrigatórios</span>

        <div className="order-actions">
          {!pending && (
            <Link className="order-button" to={backTo}>
              Voltar sem salvar
            </Link>
          )}

          <button
            className="order-button order-primary"
            type="submit"
            disabled={pending || conflict || !available}
          >
            {pending
              ? 'Salvando…'
              : initial
                ? 'Salvar alterações'
                : 'Cadastrar pedido'}
          </button>
        </div>
      </div>
    </form>
  )
}