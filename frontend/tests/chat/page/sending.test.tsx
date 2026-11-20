import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PROCESSING_DELAY_WARNING_MS } from '../../../src/features/chat/conversationOperation'
import type { ChatSessionDetail, ChatTurnResponse } from '../../../src/features/chat/types'
import { ApiError } from '../../../src/lib/api-client'
import {
  deferred, detailA, detailB, editor, messageA, messageB, read, renderReadyPage,
  replyA, replyB, select, send, sentA, sentB, sessionA, sessionB, setupChatPageTests,
  submit, turnA, turnB,
} from './helpers'

describe('ChatPage sending', () => {
  setupChatPageTests()

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sends with Enter and displays the assistant reply', async () => {
    await renderReadyPage()
    fireEvent.change(editor(), { target: { value: sentA.content } })

    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter' })

    expect(send).toHaveBeenCalledExactlyOnceWith(
      sessionA.id,
      expect.objectContaining({
        content: sentA.content,
        operation_id: expect.any(String),
      }),
      expect.any(AbortSignal),
    )
    expect(await screen.findByText(replyA.content)).toBeTruthy()
  })

  it('keeps a line break with Shift+Enter', async () => {
    await renderReadyPage()
    fireEvent.change(editor(), { target: { value: 'Linha 1\nLinha 2' } })

    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter', shiftKey: true })

    expect(send).not.toHaveBeenCalled()
    expect(editor().value).toBe('Linha 1\nLinha 2')
  })

  it('does not send empty or disabled content with Enter and shows processing status', async () => {
    const pending = deferred<ChatTurnResponse>()
    send.mockReturnValueOnce(pending.promise)
    await renderReadyPage()

    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter' })
    expect(send).not.toHaveBeenCalled()

    submit(sentA.content)
    expect(editor().disabled).toBe(true)
    expect(screen.getByRole('status').textContent).toContain('processando')
    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter' })
    expect(send).toHaveBeenCalledTimes(1)

    await act(async () => pending.resolve(turnA))
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByText(replyA.content)).toBeTruthy()
  })

  it('orders resumed messages by persisted position instead of array order', async () => {
    read.mockResolvedValueOnce({
      ...detailA,
      messages: [sentA, messageA],
    })
    await renderReadyPage()

    const log = screen.getByRole('log')
    expect(within(log).getAllByRole('article').map((article) =>
      article.querySelector('p')?.textContent,
    )).toEqual([messageA.content, sentA.content])
  })

  it('keeps a send response in A without clearing the new draft in B', async () => {
    const pending = deferred<ChatTurnResponse>()
    send.mockReturnValueOnce(pending.promise)
    await renderReadyPage()
    submit(sentA.content)
    expect(send).toHaveBeenCalledTimes(1)
    select(sessionB.title)
    await screen.findByText(messageB.content)
    expect(editor().value).toBe('')
    fireEvent.change(editor(), { target: { value: 'Rascunho de B' } })

    await act(async () => pending.resolve(turnA))

    expect(screen.queryByText(sentA.content)).toBeNull()
    expect(screen.queryByText(replyA.content)).toBeNull()
    expect(editor().value).toBe('Rascunho de B')
    expect(editor().disabled).toBe(false)
    select(sessionA.title)
    expect(await screen.findByText(sentA.content)).toBeTruthy()
    expect(screen.getByText(replyA.content)).toBeTruthy()
  })

  it('keeps pending sends independent across conversations', async () => {
    const pendingA = deferred<ChatTurnResponse>()
    const pendingB = deferred<ChatTurnResponse>()
    send.mockReturnValueOnce(pendingA.promise).mockReturnValueOnce(pendingB.promise)
    await renderReadyPage()
    submit(sentA.content)
    fireEvent.click(screen.getByRole('button', { name: 'Enviar mensagem' }))
    expect(send).toHaveBeenCalledTimes(1)
    select(sessionB.title)
    await screen.findByText(messageB.content)
    submit(sentB.content)
    expect(send).toHaveBeenNthCalledWith(
      2,
      sessionB.id,
      expect.objectContaining({
        content: sentB.content,
        operation_id: expect.any(String),
      }),
      expect.any(AbortSignal),
    )

    await act(async () => pendingA.resolve(turnA))
    expect(editor().disabled).toBe(true)
    expect(editor().value).toBe(sentB.content)
    expect(screen.queryByText(sentA.content)).toBeNull()
    await act(async () => pendingB.resolve(turnB))
    expect(screen.getByText(sentB.content)).toBeTruthy()
    expect(screen.getByText(replyB.content)).toBeTruthy()
    expect(editor().disabled).toBe(false)
    expect(editor().value).toBe('')
  })

  it.each([
    { order: 'send first', includesSent: false },
    { order: 'send first', includesSent: true },
    { order: 'read first', includesSent: false },
    { order: 'read first', includesSent: true },
  ])('merges a resumed read and send: $order, snapshot includes send=$includesSent', async ({ order, includesSent }) => {
    const pendingSend = deferred<ChatTurnResponse>()
    const pendingRead = deferred<ChatSessionDetail>()
    send.mockReturnValueOnce(pendingSend.promise)
    read.mockResolvedValueOnce(detailA).mockResolvedValueOnce(detailB).mockReturnValueOnce(pendingRead.promise)
    await renderReadyPage()
    submit(sentA.content)
    select(sessionB.title)
    await screen.findByText(messageB.content)
    select(sessionA.title)
    const snapshot = {
      ...sessionA,
      messages: includesSent ? [messageA, sentA, replyA] : [messageA],
    }

    if (order === 'send first') {
      await act(async () => pendingSend.resolve(turnA))
      expect(screen.getByText('Carregando conversa...')).toBeTruthy()
      await act(async () => pendingRead.resolve(snapshot))
    } else {
      await act(async () => pendingRead.resolve(snapshot))
      expect(editor().disabled).toBe(true)
      await act(async () => pendingSend.resolve(turnA))
    }

    const log = screen.getByRole('log')
    expect(within(log).getAllByText(sentA.content)).toHaveLength(1)
    expect(within(log).getAllByText(replyA.content)).toHaveLength(1)
    expect(within(log).getAllByRole('article').map((article) => article.querySelector('p')?.textContent))
      .toEqual([messageA.content, sentA.content, replyA.content])
    expect(editor().disabled).toBe(false)
  })

  it('preserves the draft and displays error with retry when sending fails before server persistence', async () => {
    const pending = deferred<ChatTurnResponse>()
    send.mockReturnValueOnce(pending.promise)
    await renderReadyPage()
    submit(sentA.content)

    await act(async () => pending.reject(new Error('Offline')))

    expect(screen.getByRole('alert').textContent).toContain('Não foi possível enviar a mensagem.')
    expect(editor().value).toBe(sentA.content)
    expect(editor().disabled).toBe(false)
    expect(within(screen.getByRole('log')).queryByText(sentA.content)).toBeNull()

    // Nova tentativa reutiliza o mesmo operation_id com retry: true
    const originalOpId = send.mock.calls[0][1].operation_id
    send.mockResolvedValueOnce(turnA)
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(send).toHaveBeenNthCalledWith(
      2,
      sessionA.id,
      { content: sentA.content, operation_id: originalOpId, retry: true },
      expect.any(AbortSignal),
    )
    expect(await screen.findByText(replyA.content)).toBeTruthy()
    expect(editor().value).toBe('')
  })

  it('preserves persisted user message on 502 agent error and retries without duplicating it', async () => {
    const serverError = new ApiError(502, {
      detail: 'Não foi possível obter resposta do assistente. Tente novamente.',
      operation_id: 'op-server-502',
      user_message: sentA,
    })
    send.mockRejectedValueOnce(serverError).mockResolvedValueOnce({
      ...turnA,
      operation_id: 'op-server-502',
    })
    await renderReadyPage()
    submit(sentA.content)

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Não foi possível obter resposta do assistente.',
    )
    // Mensagem do funcionário já persistida permanece visível no histórico
    expect(within(screen.getByRole('log')).getAllByText(sentA.content)).toHaveLength(1)
    expect(editor().value).toBe('')

    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(send).toHaveBeenNthCalledWith(
      2,
      sessionA.id,
      { content: sentA.content, operation_id: 'op-server-502', retry: true },
      expect.any(AbortSignal),
    )
    expect(await screen.findByText(replyA.content)).toBeTruthy()
    expect(within(screen.getByRole('log')).getAllByText(sentA.content)).toHaveLength(1)
  })

  it('shows delay warning after 60 seconds, offers retry with same operation_id, and ignores stale reply', async () => {
    const attempt1 = deferred<ChatTurnResponse>()
    const attempt2 = deferred<ChatTurnResponse>()
    send.mockReturnValueOnce(attempt1.promise).mockReturnValueOnce(attempt2.promise)
    await renderReadyPage()
    vi.useFakeTimers()

    submit(sentA.content)
    const firstOpId = send.mock.calls[0][1].operation_id
    const firstSignal = send.mock.calls[0][2]
    expect(screen.getByRole('status').textContent).toContain('processando')
    expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(PROCESSING_DELAY_WARNING_MS)
    })

    expect(screen.getByRole('status').textContent).toContain('demorando')
    const retryButton = screen.getByRole('button', { name: 'Tentar novamente' })
    fireEvent.click(retryButton)

    expect(firstSignal?.aborted).toBe(true)
    expect(send).toHaveBeenNthCalledWith(
      2,
      sessionA.id,
      { content: sentA.content, operation_id: firstOpId, retry: true },
      expect.any(AbortSignal),
    )

    // Resposta vigente da tentativa 2 conclui primeiro
    const replyV2 = {
      ...replyA,
      id: 'reply-v2',
      content: 'Resposta vigente da tentativa 2',
    }
    await act(async () => {
      attempt2.resolve({ ...turnA, assistant_message: replyV2 })
    })
    expect(screen.getByText('Resposta vigente da tentativa 2')).toBeTruthy()

    // Resposta atrasada da tentativa 1 é ignorada sem substituir nem duplicar
    const staleReply = {
      ...replyA,
      id: 'reply-stale',
      content: 'Resposta atrasada da tentativa 1',
    }
    await act(async () => {
      attempt1.resolve({ ...turnA, assistant_message: staleReply })
    })
    expect(screen.queryByText('Resposta atrasada da tentativa 1')).toBeNull()
    expect(screen.getByText('Resposta vigente da tentativa 2')).toBeTruthy()
  })

  it('associates a failed send with its original conversation', async () => {
    const pending = deferred<ChatTurnResponse>()
    send.mockReturnValueOnce(pending.promise)
    await renderReadyPage()
    submit(sentA.content)
    select(sessionB.title)
    await screen.findByText(messageB.content)

    await act(async () => pending.reject(new Error('Offline')))

    expect(screen.queryByRole('alert')).toBeNull()
    expect(editor().disabled).toBe(false)
    select(sessionA.title)
    await screen.findByText(messageA.content)
    expect(screen.getByRole('alert').textContent).toContain('Não foi possível enviar a mensagem.')
  })

  it('resets an unsent draft when switching conversations', async () => {
    await renderReadyPage()
    fireEvent.change(editor(), { target: { value: 'Rascunho de A' } })

    select(sessionB.title)
    await screen.findByText(messageB.content)

    expect(editor().value).toBe('')
    expect(send).not.toHaveBeenCalled()
  })

  it('recovers a failed operation after reopening the conversation and retries without duplicating messages', async () => {
    read.mockResolvedValueOnce({
      ...detailA,
      messages: [messageA, sentA],
      pending_operation: {
        operation_id: 'op-reopen-failed',
        status: 'failed',
        user_message_id: sentA.id,
        content: sentA.content,
        attempt: 1,
        error_detail: 'Falha anterior do agente',
        created_at: '2026-11-17T12:01:00Z',
        updated_at: '2026-11-17T12:01:05Z',
      },
    })
    send.mockResolvedValueOnce({
      ...turnA,
      operation_id: 'op-reopen-failed',
    })

    await renderReadyPage()

    expect(screen.getByRole('alert').textContent).toContain('Tente novamente')
    const retryButton = screen.getByRole('button', { name: 'Tentar novamente' })
    fireEvent.click(retryButton)

    expect(send).toHaveBeenCalledExactlyOnceWith(
      sessionA.id,
      { content: sentA.content, operation_id: 'op-reopen-failed', retry: true },
      expect.any(AbortSignal),
    )
    expect(await screen.findByText(replyA.content)).toBeTruthy()
    expect(within(screen.getByRole('log')).getAllByText(sentA.content)).toHaveLength(1)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('recovers an interrupted processing operation after reopening and reuses operation_id on resubmit', async () => {
    read.mockResolvedValueOnce({
      ...detailA,
      messages: [messageA, sentA],
      pending_operation: {
        operation_id: 'op-reopen-processing',
        status: 'processing',
        user_message_id: sentA.id,
        content: sentA.content,
        attempt: 1,
        error_detail: null,
        created_at: '2026-11-17T12:01:00Z',
        updated_at: '2026-11-17T12:01:00Z',
      },
    })
    send.mockResolvedValueOnce({
      ...turnA,
      operation_id: 'op-reopen-processing',
    })

    await renderReadyPage()

    expect(screen.getByRole('status').textContent).toContain('processamento')
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeTruthy()

    // Mesmo se o funcionário reenviar o mesmo texto pelo campo, reutiliza operation_id original
    submit(sentA.content)

    expect(send).toHaveBeenCalledExactlyOnceWith(
      sessionA.id,
      { content: sentA.content, operation_id: 'op-reopen-processing', retry: true },
      expect.any(AbortSignal),
    )
    expect(await screen.findByText(replyA.content)).toBeTruthy()
    expect(within(screen.getByRole('log')).getAllByText(sentA.content)).toHaveLength(1)
    expect(screen.queryByRole('status')).toBeNull()
  })
})
