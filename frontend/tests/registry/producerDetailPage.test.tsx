import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { ProducerDetailPage } from '../../src/features/registry/pages/ProducerDetailPage'
import { getProducer } from '../../src/features/registry/registryApi'
import type { Producer } from '../../src/features/registry/types'
import { ApiError } from '../../src/lib/api-client'

vi.mock('../../src/features/registry/registryApi', () => ({ getProducer: vi.fn() }))
const read = vi.mocked(getProducer)
const ana: Producer = {
  id: 'ana', name: 'Ana Silva', code: 'P001', cpf: '01234567890', active: true,
  municipality: 'Caruaru', address: 'Rua das Flores, 10', phone: '81999990000',
  email: 'ana@example.com', products: [{ id: 'lettuce', name: 'Alface' }],
}
const bruno: Producer = {
  id: 'bruno', name: 'Bruno Lima', code: 'P002', cpf: '12345678901', active: false,
  municipality: null, address: null, phone: null, email: null, products: [],
}

function deferredProducer() {
  let resolve!: (producer: Producer) => void
  const promise = new Promise<Producer>((resolvePromise) => { resolve = resolvePromise })
  return { promise, resolve }
}

function renderPage(producerId = ana.id) {
  return render(
    <MemoryRouter initialEntries={['/registry/producers/' + producerId]}>
      <AuthProvider>
        <Link to="/registry/producers/bruno">Abrir Bruno</Link>
        <Routes>
          <Route path="/registry/producers/:producerId" element={<ProducerDetailPage />} />
          <Route path="/registry/producers" element={<h1>Listagem de produtores</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('ProducerDetailPage', () => {
  beforeEach(() => {
    read.mockReset()
  })

  it('shows loading before displaying registration data and associated products', async () => {
    const pending = deferredProducer()
    read.mockReturnValueOnce(pending.promise)
    renderPage()

    expect(screen.getByRole('status').textContent).toContain('Carregando produtor')
    expect(read).toHaveBeenCalledExactlyOnceWith(ana.id, expect.any(AbortSignal))
    pending.resolve(ana)

    expect(await screen.findByRole('heading', { name: ana.name })).toBeTruthy()
    const registration = within(screen.getByRole('region', { name: 'Dados cadastrais' }))
    for (const value of [ana.code, ana.cpf, 'Ativo', 'Caruaru', 'Rua das Flores, 10',
      '81999990000', 'ana@example.com']) {
      expect(registration.getByText(value)).toBeTruthy()
    }
    const products = within(screen.getByRole('region', { name: 'Produtos associados' }))
    expect(products.getByRole('listitem').textContent).toBe('Alface')
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('shows missing optional fields and no associated products', async () => {
    read.mockResolvedValueOnce(bruno)
    renderPage(bruno.id)

    expect(await screen.findByRole('heading', { name: bruno.name })).toBeTruthy()
    const registration = within(screen.getByRole('region', { name: 'Dados cadastrais' }))
    for (const label of ['Município', 'Endereço', 'Telefone', 'E-mail']) {
      const term = registration.getByText(label, { selector: 'dt' })
      expect(term.nextElementSibling?.textContent).toBe('Não informado')
    }
    expect(registration.getByText('Inativo')).toBeTruthy()
    const products = within(screen.getByRole('region', { name: 'Produtos associados' }))
    expect(products.getByText('Nenhum produto associado.')).toBeTruthy()
    expect(products.queryByRole('list')).toBeNull()
  })

  it('shows a not-found message and a link back to producers', async () => {
    read.mockRejectedValueOnce(new ApiError(404, { detail: 'Producer not found.' }))
    renderPage('unknown')

    expect(await screen.findByText('Produtor não encontrado.')).toBeTruthy()
    fireEvent.click(screen.getByRole('link', { name: 'Voltar para produtores' }))
    expect(screen.getByRole('heading', { name: 'Listagem de produtores' })).toBeTruthy()
  })

  it('retries after the detail request fails', async () => {
    read.mockRejectedValueOnce(new Error('Network error')).mockResolvedValueOnce(ana)
    renderPage()

    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível carregar')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByRole('heading', { name: ana.name })).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(read).toHaveBeenCalledTimes(2)
    expect(read).toHaveBeenLastCalledWith(ana.id, expect.any(AbortSignal))
  })

  it('aborts the previous request when switching producers', async () => {
    const pending = deferredProducer()
    read.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(bruno)
    renderPage()
    const signal = read.mock.calls[0][1]
    expect(signal?.aborted).toBe(false)

    fireEvent.click(screen.getByRole('link', { name: 'Abrir Bruno' }))
    expect(signal?.aborted).toBe(true)
    expect(await screen.findByRole('heading', { name: bruno.name })).toBeTruthy()

    await act(async () => { pending.resolve(ana) })
    expect(screen.getByRole('heading', { name: bruno.name })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: ana.name })).toBeNull()
  })
})
