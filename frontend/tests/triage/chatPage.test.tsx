import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { PROCESSING_DELAY_WARNING_MS } from '../../src/features/chat/conversationOperation'
import { TriageChatPage } from '../../src/features/triage/pages/TriageChatPage'
import {
  finalizeSolicitation,
  openSolicitationSession,
  sendSolicitationMessage,
} from '../../src/features/triage/triageApi'
import type {
  SolicitationSession,
  SolicitationTurnResponse,
} from '../../src/features/triage/types'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/triage/triageApi', () => ({
  finalizeSolicitation: vi.fn(),
  openSolicitationSession: vi.fn(),
  sendSolicitationMessage: vi.fn(),
}))

// Draft review is tested separately; avoid real HTTP in triage page tests.
vi.mock('../../src/features/orders/orderDraftsApi', () => ({
  getOrderDraft: vi.fn(async () => ({ draft: null, order: null })),
  confirmOrderDraft: vi.fn(),
}))

const read = vi.mocked(openSolicitationSession)
const send = vi.mocked(sendSolicitationMessage)
const finalize = vi.mocked(finalizeSolicitation)
const timestamp = '2026-10-30T16:00:00Z'
const session: SolicitationSession = {
  id: 'solicitation-a',
  session_id: 'session-a',
  summary: 'Oferta de queijo coalho com pedido de retorno.',
  request_type: 'oferta',
  urgency: 'urgente',
  status: 'em_analise',
  title: 'PED-2026-015',
  created_at: timestamp,
  read_only: false,
  messages: [
    {
      id: 'message-original',
      role: 'user',
      content: 'Tenho 200 kg de queijo coalho. Me avisa até amanhã.',
      position: 1,
      created_at: timestamp,
      citations: [],
    },
    {
      id: 'message-analysis',
      role: 'assistant',
      content: 'Análise inicial da triagem\nPrazo: 31/10/2026\nPendências:\n- Verificar pedidos da semana.',
      position: 2,
      created_at: timestamp,
      citations: [],
    },
  ],
}
const solved: SolicitationSession = {
  ...session,
  status: 'finalizada',
  read_only: true,
}
const clarification = {
  id: 'message-clarification',
  role: 'user',
  content: 'Há pedidos para o produtor nesta semana.',
  position: 3,
  created_at: timestamp,
  citations: [],
}
const updatedAssistantMessage = {
  id: 'message-analysis-updated',
  role: 'assistant',
  content: 'Análise atualizada: entrega reagendada para 05/11/2026 sem pendências.',
  position: 4,
  created_at: timestamp,
  citations: [],
}
const clarificationTurn: SolicitationTurnResponse = {
  operation_id: 'op-triage-1',
  selected_flow: 'triage',
  user_message: clarification,
  assistant_message: updatedAssistantMessage,
  solicitation: {
    id: session.id,
    session_id: session.session_id,
    summary: 'Pedido atualizado de queijo coalho para 05/11/2026.',
    request_type: 'pedido',
    urgency: 'normal',
    status: 'em_analise',
  },
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function renderPage(solicitationId = session.id) {
  return render(
    <MemoryRouter initialEntries={[`/triagem/${solicitationId}`]}>
      <AuthProvider>
        <Routes>
          <Route path="/triagem" element={<h1>Fila de triagem</h1>} />
          <Route path="/triagem/:solicitationId" element={<TriageChatPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

function editor() {
  return screen.getByRole<HTMLTextAreaElement>('textbox', {
    name: 'Mensagem para o assistente',
  })
}

function submit(content: string) {
  fireEvent.change(editor(), { target: { value: content } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar mensagem' }))
}

describe('TriageChatPage', () => {
  beforeEach(() => {
    localStorage.clear()
    setAccessToken('test-token')
    read.mockReset().mockResolvedValue(session)
    send.mockReset().mockResolvedValue(clarificationTurn)
    finalize.mockReset().mockResolvedValue({
      id: session.id,
      session_id: session.session_id,
      summary: session.summary,
      request_type: session.request_type,
      urgency: session.urgency,
      status: 'finalizada',
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  it('loads the shared history with original message and initial analysis', async () => {
    const pending = deferred<SolicitationSession>()
    read.mockReturnValueOnce(pending.promise)
    renderPage()

    expect(screen.getByRole('status').textContent).toBe('Carregando solicitação…')
    expect(read).toHaveBeenCalledExactlyOnceWith(
      session.id,
      expect.any(AbortSignal),
    )
    await act(async () => pending.resolve(session))

    expect(
      await screen.findByRole('heading', { name: session.summary }),
    ).toBeTruthy()
    for (const value of ['Em análise', 'Urgente', 'Oferta']) {
      expect(screen.getByText(value)).toBeTruthy()
    }

    const log = screen.getByRole('log')
    expect(within(log).getByText('Mensagem original')).toBeTruthy()
    expect(within(log).getByText(session.messages[0].content)).toBeTruthy()
    expect(within(log).getByText('Assistente')).toBeTruthy()
    expect(within(log).getByText(/Análise inicial da triagem/)).toBeTruthy()
    expect(within(log).getByText(/Prazo: 31\/10\/2026/)).toBeTruthy()
    expect(editor().disabled).toBe(false)
  })

  it('sends a clarification, shows processing status, displays assistant reply and updates card without changing status', async () => {
    const pending = deferred<SolicitationTurnResponse>()
    send.mockReturnValueOnce(pending.promise)
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    submit(clarification.content)

    expect(send).toHaveBeenCalledExactlyOnceWith(
      session.id,
      expect.objectContaining({
        content: clarification.content,
        operation_id: expect.any(String),
      }),
      expect.any(AbortSignal),
    )
    expect(editor().disabled).toBe(true)
    expect(screen.getByRole('status').textContent).toContain('processando')
    await act(async () => pending.resolve(clarificationTurn))

    const log = screen.getByRole('log')
    expect(within(log).getByText('Funcionário')).toBeTruthy()
    expect(within(log).getByText(clarification.content)).toBeTruthy()
    expect(within(log).getByText(updatedAssistantMessage.content)).toBeTruthy()
    // Cartão atualizado (resumo, tipo e urgência) preservando o estado Em análise e a mensagem original
    expect(
      screen.getByRole('heading', { name: clarificationTurn.solicitation.summary }),
    ).toBeTruthy()
    expect(screen.getByText('Em análise')).toBeTruthy()
    expect(screen.getByText('Normal')).toBeTruthy()
    expect(screen.getByText('Pedido')).toBeTruthy()
    expect(within(log).getByText(session.messages[0].content)).toBeTruthy()
    expect(editor().value).toBe('')
    expect(editor().disabled).toBe(false)
  })

  it('preserves the draft and shows an error with retry when sending fails', async () => {
    send.mockRejectedValueOnce(new Error('Offline'))
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    submit('Mensagem que não foi enviada')

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Não foi possível enviar a mensagem.',
    )
    expect(editor().value).toBe('Mensagem que não foi enviada')
    expect(screen.queryByText('Funcionário')).toBeNull()
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeTruthy()
  })

  it('preserves user message on 502 agent failure and retries with same operation_id without duplicating', async () => {
    send
      .mockRejectedValueOnce(
        new ApiError(502, {
          detail: 'Não foi possível obter resposta do assistente. Tente novamente.',
          operation_id: 'op-triage-502',
          user_message: clarification,
        }),
      )
      .mockResolvedValueOnce({
        ...clarificationTurn,
        operation_id: 'op-triage-502',
      })
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    submit(clarification.content)

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Não foi possível obter resposta do assistente.',
    )
    expect(within(screen.getByRole('log')).getAllByText(clarification.content)).toHaveLength(1)
    expect(screen.getByRole('heading', { name: session.summary })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(send).toHaveBeenNthCalledWith(
      2,
      session.id,
      { content: clarification.content, operation_id: 'op-triage-502', retry: true },
      expect.any(AbortSignal),
    )
    expect(await screen.findByText(updatedAssistantMessage.content)).toBeTruthy()
    expect(within(screen.getByRole('log')).getAllByText(clarification.content)).toHaveLength(1)
  })

  it('warns after 60 seconds, retries with same operation_id, and ignores stale analysis', async () => {
    vi.useFakeTimers()
    const attempt1 = deferred<SolicitationTurnResponse>()
    const attempt2 = deferred<SolicitationTurnResponse>()
    send.mockReturnValueOnce(attempt1.promise).mockReturnValueOnce(attempt2.promise)
    renderPage()
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByRole('heading', { name: session.summary })).toBeTruthy()

    submit(clarification.content)
    const firstOpId = send.mock.calls[0][1].operation_id
    const firstSignal = send.mock.calls[0][2]

    await act(async () => {
      vi.advanceTimersByTime(PROCESSING_DELAY_WARNING_MS)
    })

    expect(screen.getByRole('status').textContent).toContain('demorando')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(firstSignal?.aborted).toBe(true)
    expect(send).toHaveBeenNthCalledWith(
      2,
      session.id,
      { content: clarification.content, operation_id: firstOpId, retry: true },
      expect.any(AbortSignal),
    )

    await act(async () => attempt2.resolve(clarificationTurn))
    expect(
      screen.getByRole('heading', { name: clarificationTurn.solicitation.summary }),
    ).toBeTruthy()

    // Resultado atrasado da tentativa 1 não substitui a análise vigente
    await act(async () => {
      attempt1.resolve({
        ...clarificationTurn,
        assistant_message: {
          ...updatedAssistantMessage,
          id: 'stale-msg',
          content: 'Análise atrasada',
        },
        solicitation: {
          ...clarificationTurn.solicitation,
          summary: 'Resumo atrasado',
          urgency: 'urgente',
        },
      })
    })
    expect(screen.queryByText('Análise atrasada')).toBeNull()
    expect(
      screen.getByRole('heading', { name: clarificationTurn.solicitation.summary }),
    ).toBeTruthy()
  })

  it('switches to read-only when another employee finalized the conversation', async () => {
    send.mockRejectedValueOnce(new ApiError(409, null))
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    submit('Mensagem atrasada')

    expect((await screen.findByRole('alert')).textContent).toContain(
      'A conversa foi finalizada e não aceita novas mensagens.',
    )
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByText('Finalizada')).toBeTruthy()
    expect(screen.getByText(/permanece disponível/)).toBeTruthy()
  })

  it('finalizes without service after confirming and remains consultable', async () => {
    const pending = deferred<Awaited<ReturnType<typeof finalizeSolicitation>>>()
    finalize.mockReturnValueOnce(pending.promise)
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    fireEvent.click(screen.getByRole('button', { name: 'Encerrar solicitação' }))
    const confirmation = screen.getByRole('group', {
      name: 'Confirmar encerramento da solicitação',
    })
    expect(finalize).not.toHaveBeenCalled()
    fireEvent.click(within(confirmation).getByRole('button', {
      name: 'Confirmar encerramento',
    }))
    expect(finalize).toHaveBeenCalledExactlyOnceWith(session.id)
    expect(within(confirmation).getByRole<HTMLButtonElement>('button', {
      name: 'Finalizando…',
    }).disabled).toBe(true)

    await act(async () => pending.resolve({
      id: session.id,
      session_id: session.session_id,
      summary: session.summary,
      request_type: session.request_type,
      urgency: session.urgency,
      status: 'finalizada',
    }))

    expect(screen.getByText(
      'Solicitação finalizada. A conversa permanece disponível para consulta.',
    )).toBeTruthy()
    expect(screen.getByText('Finalizada')).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Encerrar solicitação' })).toBeNull()
    expect(
      within(screen.getByRole('log')).getByText(/Análise inicial da triagem/),
    ).toBeTruthy()
  })

  it('cancels finalization without calling the API', async () => {
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    fireEvent.click(screen.getByRole('button', { name: 'Encerrar solicitação' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(finalize).not.toHaveBeenCalled()
    expect(screen.queryByRole('group')).toBeNull()
    expect(editor().disabled).toBe(false)
  })

  it('opens a finalized solicitation in read-only mode', async () => {
    read.mockResolvedValueOnce(solved)
    renderPage()

    await screen.findByRole('heading', { name: session.summary })

    expect(screen.getByText('Finalizada')).toBeTruthy()
    expect(screen.getByText(/somente para consulta/)).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Encerrar solicitação' })).toBeNull()
    expect(within(screen.getByRole('log')).getByText(session.messages[0].content)).toBeTruthy()
  })

  it('shows a not-found state and returns to the queue', async () => {
    read.mockRejectedValueOnce(new ApiError(404, null))
    renderPage('unknown')

    expect(
      await screen.findByRole('heading', { name: 'Solicitação não encontrada' }),
    ).toBeTruthy()
    fireEvent.click(screen.getByRole('link', { name: '← Voltar para a fila' }))

    expect(screen.getByRole('heading', { name: 'Fila de triagem' })).toBeTruthy()
  })

  it('retries a failed load', async () => {
    read.mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce(session)
    renderPage()

    expect((await screen.findByRole('alert')).textContent)
      .toBe('Não foi possível carregar a solicitação.')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(
      await screen.findByRole('heading', { name: session.summary }),
    ).toBeTruthy()
    expect(read).toHaveBeenCalledTimes(2)
  })

  it('aborts the active read on unmount', async () => {
    const pending = deferred<SolicitationSession>()
    read.mockReturnValueOnce(pending.promise)
    const { unmount } = renderPage()
    const signal = read.mock.calls[0][1]

    expect(signal?.aborted).toBe(false)
    unmount()
    expect(signal?.aborted).toBe(true)
  })

  it('logs out when the session read returns 401', async () => {
    read.mockRejectedValueOnce(new ApiError(401, null))
    renderPage()

    await waitFor(() => expect(getAccessToken()).toBeNull())
  })
})
