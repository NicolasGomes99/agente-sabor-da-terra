import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { ProductsPage } from '../../src/features/registry/pages/ProductsPage'
import { listProducts } from '../../src/features/registry/registryApi'
import type { Product } from '../../src/features/registry/types'

vi.mock('../../src/features/registry/registryApi', () => ({ listProducts: vi.fn() }))
const list = vi.mocked(listProducts)
const catalog = [{ id: 'first', name: 'Açafrão' }, { id: 'second', name: 'Alface' }]

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><ProductsPage /></AuthProvider>
    </MemoryRouter>,
  )
}

describe('ProductsPage', () => {
  beforeEach(() => {
    list.mockReset().mockResolvedValue(catalog)
  })

  it('shows loading before displaying the product names', async () => {
    let resolve!: (products: Product[]) => void
    const promise = new Promise<Product[]>((resolvePromise) => {
      resolve = resolvePromise
    })
    list.mockReturnValueOnce(promise)
    renderPage()

    expect(screen.getByRole('status').textContent).toContain('Carregando produtos')
    expect(screen.queryByRole('listitem')).toBeNull()
    resolve(catalog)

    expect((await screen.findAllByRole('listitem')).map((item) => item.textContent))
      .toEqual(['Açafrão', 'Alface'])
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('filters by partial name and restores the catalog when cleared', async () => {
    renderPage()
    const search = await screen.findByRole('searchbox', { name: 'Buscar por nome' })

    fireEvent.change(search, { target: { value: '  CAFRA  ' } })
    expect(screen.getByText('Açafrão')).toBeTruthy()
    expect(screen.queryByText('Alface')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Limpar busca' }))
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Alface')).toBeTruthy()
  })

  it('shows a distinct message when the search has no matches', async () => {
    renderPage()
    const search = await screen.findByRole('searchbox', { name: 'Buscar por nome' })

    fireEvent.change(search, { target: { value: 'Mamão' } })
    expect(screen.getByRole('status').textContent).toBe('Nenhum produto corresponde à busca.')
    expect(screen.queryByRole('listitem')).toBeNull()
  })

  it('shows the empty catalog message', async () => {
    list.mockResolvedValueOnce([])
    renderPage()

    expect(await screen.findByText('Nenhum produto cadastrado.')).toBeTruthy()
    expect(screen.queryByRole('searchbox')).toBeNull()
  })

  it('retries after a catalog request fails', async () => {
    list.mockRejectedValueOnce(new Error('Network error'))
    renderPage()

    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível carregar')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByText('Açafrão')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('aborts the catalog request on unmount', () => {
    list.mockReturnValueOnce(new Promise<Product[]>(() => {}))
    const { unmount } = renderPage()
    const signal = list.mock.calls[0][0]

    expect(signal?.aborted).toBe(false)
    unmount()
    expect(signal?.aborted).toBe(true)
  })
})
