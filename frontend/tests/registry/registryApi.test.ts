import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getProducer, listProducers, listProducts } from '../../src/features/registry/registryApi'
import { ApiError } from '../../src/lib/api-client'
import { clearAccessToken, setAccessToken } from '../../src/lib/auth-storage'

const product = { id: 'fc46e9db-b452-4fa1-bec5-5a1eb3472eb3', name: 'Alface' }
const producer = {
  id: '48594118-ef09-4e47-a96c-78848b961120',
  code: 'P001',
  name: 'Ana Silva',
  cpf: '01234567890',
  active: true,
  phone: null,
  email: null,
  address: null,
  municipality: 'Caruaru',
  products: [product],
}
const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const fetchMock = vi.fn<typeof fetch>()

describe('registry API', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('test-token')
  })

  afterEach(() => {
    clearAccessToken()
    vi.unstubAllGlobals()
  })

  it('lists products with the bearer token and abort signal', async () => {
    const { signal } = new AbortController()
    fetchMock.mockResolvedValueOnce(Response.json([product]))

    await expect(listProducts(signal)).resolves.toEqual([product])
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      baseUrl + '/products', expect.objectContaining({ signal }),
    )
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization'))
      .toBe('Bearer test-token')
  })

  it.each([
    { productId: undefined, path: '/producers' },
    { productId: product.id, path: '/producers?product_id=' + product.id },
  ])('lists producers with or without a product filter ($path)', async ({ productId, path }) => {
    fetchMock.mockResolvedValueOnce(Response.json([producer]))

    await expect(listProducers(productId)).resolves.toEqual([producer])
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(baseUrl + path, expect.any(Object))
  })

  it('loads a producer with associated products and nullable fields', async () => {
    fetchMock.mockResolvedValueOnce(Response.json(producer))

    await expect(getProducer(producer.id)).resolves.toEqual(producer)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      baseUrl + '/producers/' + producer.id, expect.any(Object),
    )
  })

  it.each([
    { status: 401, detail: 'Could not validate credentials.', request: () => listProducers() },
    { status: 404, detail: 'Producer not found.', request: () => getProducer(producer.id) },
  ])('propagates unauthorized and not found responses ($status)', async ({ status, detail, request }) => {
    fetchMock.mockResolvedValueOnce(Response.json({ detail }, { status }))

    const result = request()

    await expect(result).rejects.toBeInstanceOf(ApiError)
    await expect(result).rejects.toMatchObject({ status, details: { detail } })
  })
})
