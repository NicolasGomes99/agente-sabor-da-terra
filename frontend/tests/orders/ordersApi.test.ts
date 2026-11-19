import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'

import {
  cancelOrder,
  createOrder,
  getOrder,
  listOrders,
  updateOrder,
  type OrderInput,
  type OrderRecord,
  type OrderUpdate,
} from '../../src/features/orders/ordersApi'
import {
  clearAccessToken,
  setAccessToken,
} from '../../src/lib/auth-storage'

const payload: OrderInput = {
  buyer: 'Mercado de teste',
  conditions: 'Entregar pela manhã',
  delivery_start_date: '2026-12-05',
  delivery_end_date: null,
  items: [
    {
      product_id: 'product-id',
      quantity: '10.125',
      unit: 'kg',
    },
  ],
}

const record: OrderRecord = {
  ...payload,
  id: 'order-id',
  session_id: null,
  version: 1,
  cancelled: false,
  products: '',
  needs_item_structuring: false,
  items: [
    {
      ...payload.items[0],
      id: 'item-id',
      product: {
        id: 'product-id',
        name: 'Tomate',
      },
    },
  ],
}

const base =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const fetchMock = vi.fn<typeof fetch>()

describe('API de pedidos', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('test-token')
  })

  afterEach(() => {
    clearAccessToken()
    vi.unstubAllGlobals()
  })

  it('lista pedidos enviando o JWT e o sinal de cancelamento', async () => {
    fetchMock.mockResolvedValue(Response.json([record]))

    const { signal } = new AbortController()
    const result = await listOrders(signal)

    expect(result).toEqual([record])

    const [url, options] = fetchMock.mock.calls[0]

    expect(url).toBe(`${base}/orders`)
    expect(options?.signal).toBe(signal)
    expect(
      new Headers(options?.headers).get('Authorization'),
    ).toBe('Bearer test-token')
  })

  it('cadastra itens estruturados sem enviar IDs ou descrição antiga', async () => {
    fetchMock.mockResolvedValue(
      Response.json(record, { status: 201 }),
    )

    const result = await createOrder(payload)

    expect(result).toEqual(record)

    const [url, options] = fetchMock.mock.calls[0]
    const body = JSON.parse(options?.body as string)

    expect(url).toBe(`${base}/orders`)
    expect(options?.method).toBe('POST')
    expect(body).toEqual(payload)
    expect(body).not.toHaveProperty('products')
    expect(body).not.toHaveProperty('id')
    expect(body.items[0]).not.toHaveProperty('id')
    expect(
      new Headers(options?.headers).get('Content-Type'),
    ).toBe('application/json')
  })

  it('envia PUT preservando o ID do item existente', async () => {
    const edited: OrderUpdate = {
      ...payload,
      version: record.version,
      items: [
        {
          id: 'item-id',
          product_id: 'product-id',
          quantity: '12.500',
          unit: 'caixa',
        },
      ],
    }

    const updatedRecord: OrderRecord = {
      ...record,
      items: [
        {
          ...record.items[0],
          quantity: '12.500',
          unit: 'caixa',
        },
      ],
    }

    fetchMock.mockResolvedValue(Response.json(updatedRecord))

    const result = await updateOrder(record.id, edited)
    const [url, options] = fetchMock.mock.calls[0]

    expect(url).toBe(`${base}/orders/order-id`)
    expect(options?.method).toBe('PUT')
    expect(JSON.parse(options?.body as string)).toEqual(edited)
    expect(result.items[0].id).toBe('item-id')
    expect(result.items[0].quantity).toBe('12.500')
  })

  it('consulta um pedido pelo identificador', async () => {
    fetchMock.mockResolvedValue(Response.json(record))

    const result = await getOrder(record.id)

    expect(result).toEqual(record)
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${base}/orders/order-id`,
    )
  })

  it('cancela pelo endpoint correto e recebe os itens preservados', async () => {
    fetchMock.mockResolvedValue(
      Response.json({ ...record, cancelled: true }),
    )

    const result = await cancelOrder(record.id)
    const [url, options] = fetchMock.mock.calls[0]

    expect(url).toBe(`${base}/orders/order-id/cancel`)
    expect(options?.method).toBe('POST')
    expect(result.cancelled).toBe(true)
    expect(result.items).toEqual(record.items)
  })
})