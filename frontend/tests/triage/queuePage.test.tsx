import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { TriageQueuePage } from '../../src/features/triage/pages/TriageQueuePage'
import { listSolicitations } from '../../src/features/triage/triageApi'
import type { Solicitation } from '../../src/features/triage/types'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/triage/triageApi', () => ({
  listSolicitations: vi.fn(),
}))

const list = vi.mocked(listSolicitations)
const received: Solicitation = {
  id: 'solicitation-a',
  session_id: 'session-a',
  summary: 'Pedido de 200 kg de tomate.',
  request_type: 'pedido',
  urgency: 'urgente',
  status: 'recebida',
}
const inReview: Solicitation = {
  id: 'solicitation-b',
  session_id: 'session-b',
  summary: 'Consulta sobre documentos cadastrais.',
  request_type: 'consulta',
  urgency: 'normal',
  status: 'em_analise',
}
const finished: Solicitation = {
  id: 'solicitation-c',
  session_id: 'session-c',
  summary: 'Oferta de queijo coalho.',
  request_type: 'oferta',
  urgency: 'indeterminada',
  status: 'finalizada',
}
const solicitations = [received, inReview, finished]

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><TriageQueuePage /></AuthProvider>
    </MemoryRouter>,
  )
}

function search() {
  return screen.getByRole<HTMLInputElement>('searchbox', {
    name: 'Buscar solicitações',
  })
}

describe('TriageQueuePage', () => {
  beforeEach(() => {
    localStorage.clear()
    setAccessToken('test-token')
    list.mockReset().mockResolvedValue(solicitations)
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('shows loading and then the cards with status, type and urgency', async () => {
    const pending = deferred<Solicitation[]>()
    list.mockReturnValueOnce(pending.promise)
    renderPage()

    expect(screen.getByRole('status').textContent).toBe('Carregando solicitações…')
    expect(list).toHaveBeenCalledExactlyOnceWith(expect.any(AbortSignal))
    await act(async () => pending.resolve(solicitations))

    const cards = await screen.findAllByRole('listitem')
    expect(cards).toHaveLength(3)
    expect(screen.getByText('3 solicitações')).toBeTruthy()

    const receivedCard = within(cards[0])
    for (const value of ['Recebida', 'Urgente', 'Pedido', received.summary]) {
      expect(receivedCard.getByText(value)).toBeTruthy()
    }
    expect(
      receivedCard.getByText('Urgente').getAttribute('data-urgency'),
    ).toBe('urgente')
    const reviewCard = within(cards[1])
    for (const value of ['Em análise', 'Normal', 'Consulta', inReview.summary]) {
      expect(reviewCard.getByText(value)).toBeTruthy()
    }
    const finishedCard = within(cards[2])
    for (const value of ['Finalizada', 'Indeterminada', 'Oferta', finished.summary]) {
      expect(finishedCard.getByText(value)).toBeTruthy()
    }

    expect(receivedCard.getByRole('link', { name: new RegExp(received.summary) }).getAttribute('href'))
      .toBe(`/triagem/${received.id}`)
  })

  it('combines search, status, urgency and type filters', async () => {
    renderPage()
    await screen.findAllByRole('listitem')

    fireEvent.change(search(), { target: { value: 'tomate' } })
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText(received.summary)).toBeTruthy()
    expect(screen.getByText('1 solicitação')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Limpar' }))
    expect(screen.getAllByRole('listitem')).toHaveLength(3)

    fireEvent.change(screen.getByLabelText('Estado'), {
      target: { value: 'finalizada' },
    })
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText(finished.summary)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Limpar' }))
    fireEvent.change(screen.getByLabelText('Urgência'), {
      target: { value: 'urgente' },
    })
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText(received.summary)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Limpar' }))
    fireEvent.change(screen.getByLabelText('Tipo'), {
      target: { value: 'consulta' },
    })
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText(inReview.summary)).toBeTruthy()
  })

  it('offers a clear action when filters have no matches', async () => {
    renderPage()
    await screen.findAllByRole('listitem')

    fireEvent.change(search(), { target: { value: 'inexistente' } })

    expect(screen.getByText('Nenhuma solicitação encontrada.')).toBeTruthy()
    expect(screen.queryByRole('listitem')).toBeNull()
    fireEvent.click(
      screen.getByRole('button', { name: 'Limpar busca e filtros' }),
    )

    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(search().value).toBe('')
  })

  it('shows the empty queue state', async () => {
    list.mockResolvedValueOnce([])
    renderPage()

    expect(await screen.findByText('Nenhuma solicitação na fila.')).toBeTruthy()
    expect(screen.getByText('0 solicitações')).toBeTruthy()
  })

  it('retries a failed listing and reloads from the first attempt', async () => {
    list.mockRejectedValueOnce(new Error('Offline'))
    renderPage()

    expect((await screen.findByRole('alert')).textContent)
      .toBe('Não foi possível carregar a fila de triagem.')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(await screen.findByText(received.summary)).toBeTruthy()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('reloads the queue on demand', async () => {
    renderPage()
    await screen.findByText(received.summary)

    list.mockResolvedValueOnce([finished])
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar fila' }))

    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(1))
    expect(screen.getByText(finished.summary)).toBeTruthy()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('aborts the active request on unmount', async () => {
    const pending = deferred<Solicitation[]>()
    list.mockReturnValueOnce(pending.promise)
    const { unmount } = renderPage()
    const signal = list.mock.calls[0][0]

    expect(signal?.aborted).toBe(false)
    unmount()
    expect(signal?.aborted).toBe(true)
  })

  it('logs out when the listing returns 401', async () => {
    list.mockRejectedValueOnce(new ApiError(401, null))
    renderPage()

    await waitFor(() => expect(getAccessToken()).toBeNull())
  })
})
