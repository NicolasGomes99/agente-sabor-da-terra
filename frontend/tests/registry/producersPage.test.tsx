import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { ProducersPage } from '../../src/features/registry/pages/ProducersPage'
import { listProducers, listProducts } from '../../src/features/registry/registryApi'
import type { Producer } from '../../src/features/registry/types'

vi.mock('../../src/features/registry/registryApi', () => ({
  listProducers: vi.fn(),
  listProducts: vi.fn(),
}))

const producerList = vi.mocked(listProducers)
const productList = vi.mocked(listProducts)
const lettuce = { id: 'lettuce', name: 'Alface' }
const pumpkin = { id: 'pumpkin', name: 'Abóbora' }
const ana: Producer = {
  id: 'ana', code: 'P001', name: 'Ána Silva', cpf: '01234567890', active: true,
  municipality: 'Caruaru', phone: null, email: null, address: null, products: [lettuce, pumpkin],
}
const bruno: Producer = {
  ...ana, id: 'bruno', code: 'P002', name: 'Bruno Lima', cpf: '12345678901',
  active: false, municipality: null, products: [lettuce],
}
const clara: Producer = {
  ...ana, id: 'clara', code: 'P003', name: 'Clara Souza', cpf: '23456789012', products: [pumpkin],
}
const producers = [ana, bruno, clara]

function deferredProducers() {
  let resolve!: (data: Producer[]) => void
  const promise = new Promise<Producer[]>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function LocationProbe() {
  return <span data-testid="location-search">{useLocation().search}</span>
}

function renderPage(query = '') {
  return render(
    <MemoryRouter initialEntries={['/registry/producers' + query]}>
      <AuthProvider>
        <ProducersPage />
        <LocationProbe />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function currentParams() {
  return new URLSearchParams(screen.getByTestId('location-search').textContent ?? '')
}

describe('ProducersPage', () => {
  beforeEach(() => {
    productList.mockReset().mockResolvedValue([lettuce, pumpkin])
    producerList.mockReset().mockImplementation(async (productId) =>
      productId ? producers.filter(({ products }) => products.some(({ id }) => id === productId)) : producers)
  })

  it('shows loading before listing active and inactive producers', async () => {
    const pending = deferredProducers()
    producerList.mockReturnValueOnce(pending.promise)
    renderPage()

    expect(screen.getByText('Carregando produtores…')).toBeTruthy()
    expect(screen.queryByRole('listitem')).toBeNull()
    pending.resolve(producers)

    const [first, second] = await screen.findAllByRole('listitem')
    for (const value of [ana.name, ana.code, 'Caruaru', 'Ativo']) {
      expect(within(first).getByText(value)).toBeTruthy()
    }
    for (const value of [bruno.name, bruno.code, 'Não informado', 'Inativo']) {
      expect(within(second).getByText(value)).toBeTruthy()
    }
    expect(screen.queryByText('Carregando produtores…')).toBeNull()
  })

  it.each(['  ANA S  ', '  p001  '])(
    'combines name or code search with the product filter and clears both (%j)',
    async (value) => {
      renderPage()
      await screen.findByText(clara.name)
      await screen.findByRole('option', { name: lettuce.name })
      const search = screen.getByRole('searchbox', { name: 'Buscar por nome ou código' })
      const filter = screen.getByRole('combobox', { name: 'Produto fornecido' })

      fireEvent.change(filter, { target: { value: lettuce.id } })
      await screen.findByText(ana.name)
      expect(screen.getByText(bruno.name)).toBeTruthy()
      expect(screen.queryByText(clara.name)).toBeNull()
      expect(producerList).toHaveBeenLastCalledWith(lettuce.id, expect.any(AbortSignal))

      fireEvent.change(search, { target: { value } })
      expect(screen.getByText(ana.name)).toBeTruthy()
      expect(screen.getAllByRole('listitem')).toHaveLength(1)
      expect(currentParams().get('q')).toBe(value)
      expect(currentParams().get('product_id')).toBe(lettuce.id)
      expect(producerList).toHaveBeenCalledTimes(2)

      fireEvent.click(screen.getByRole('button', { name: 'Limpar busca e filtro' }))
      expect(await screen.findAllByRole('listitem')).toHaveLength(3)
      expect(currentParams().toString()).toBe('')
      expect((search as HTMLInputElement).value).toBe('')
      expect((filter as HTMLSelectElement).value).toBe('')
    },
  )

  it.each([
    {
      query: '?product_id=pumpkin', filtered: [], base: [],
      message: 'Nenhum produtor cadastrado.',
    },
    {
      query: '?product_id=pumpkin', filtered: [], base: [bruno],
      message: 'Nenhum produtor fornece o produto selecionado.',
    },
    {
      query: '?q=sem-correspondencia', filtered: undefined, base: producers,
      message: 'Nenhum produtor corresponde à busca.',
    },
  ])('distinguishes an empty base, a product without suppliers and a search without matches ($message)',
    async ({ query, filtered, base, message }) => {
      if (filtered !== undefined) producerList.mockResolvedValueOnce(filtered)
      producerList.mockResolvedValueOnce(base)
      renderPage(query)

      expect(await screen.findByText(message)).toBeTruthy()
      expect(screen.queryByRole('listitem')).toBeNull()
      if (filtered !== undefined) {
        expect(producerList).toHaveBeenNthCalledWith(1, pumpkin.id, expect.any(AbortSignal))
      }
      expect(producerList).toHaveBeenLastCalledWith(undefined, expect.any(AbortSignal))
      expect(producerList).toHaveBeenCalledTimes(filtered === undefined ? 1 : 2)
    },
  )

  it.each(['catalog', 'listing'])('retries the failed request independently (%s)', async (request) => {
    const failed = request === 'catalog' ? productList : producerList
    const other = request === 'catalog' ? producerList : productList
    failed.mockRejectedValueOnce(new Error('Network error'))
    renderPage()

    expect(await screen.findByRole('alert')).toBeTruthy()
    const retry = request === 'catalog'
      ? 'Tentar carregar produtos novamente'
      : 'Tentar carregar produtores novamente'
    fireEvent.click(screen.getByRole('button', { name: retry }))

    expect(await screen.findByText(ana.name)).toBeTruthy()
    expect(await screen.findByRole('option', { name: lettuce.name })).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(failed).toHaveBeenCalledTimes(2)
    expect(other).toHaveBeenCalledTimes(1)
  })

  it('aborts an outdated product filter and ignores its late response', async () => {
    const pending = deferredProducers()
    renderPage()
    await screen.findByText(bruno.name)
    await screen.findByRole('option', { name: lettuce.name })
    const filter = screen.getByRole('combobox', { name: 'Produto fornecido' })

    producerList.mockReturnValueOnce(pending.promise)
    fireEvent.change(filter, { target: { value: lettuce.id } })
    const signal = producerList.mock.lastCall?.[1]
    expect(signal?.aborted).toBe(false)

    fireEvent.change(filter, { target: { value: pumpkin.id } })
    expect(signal?.aborted).toBe(true)
    await screen.findByText(clara.name)

    await act(async () => { pending.resolve([ana, bruno]) })
    expect(screen.getByText(clara.name)).toBeTruthy()
    expect(screen.queryByText(bruno.name)).toBeNull()
  })
})
