import { act, fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ChatMessage, ChatSessionDetail } from '../../../src/features/chat/types'
import {
  deferred, detailA, detailB, editor, messageA, messageB, read, renderReadyPage,
  select, send, sentA, sentB, sessionA, sessionB, setupChatPageTests, submit,
} from './helpers'

describe('ChatPage sending', () => {
  setupChatPageTests()

  it('sends with Enter', async () => {
    await renderReadyPage()
    fireEvent.change(editor(), { target: { value: sentA.content } })

    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter' })

    expect(send).toHaveBeenCalledExactlyOnceWith(sessionA.id, { content: sentA.content })
  })

  it('keeps a line break with Shift+Enter', async () => {
    await renderReadyPage()
    fireEvent.change(editor(), { target: { value: 'Linha 1\nLinha 2' } })

    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter', shiftKey: true })

    expect(send).not.toHaveBeenCalled()
    expect(editor().value).toBe('Linha 1\nLinha 2')
  })

  it('does not send empty or disabled content with Enter', async () => {
    const pending = deferred<ChatMessage>()
    send.mockReturnValueOnce(pending.promise)
    await renderReadyPage()

    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter' })
    expect(send).not.toHaveBeenCalled()

    submit(sentA.content)
    expect(editor().disabled).toBe(true)
    fireEvent.keyDown(editor(), { key: 'Enter', code: 'Enter' })
    expect(send).toHaveBeenCalledExactlyOnceWith(sessionA.id, { content: sentA.content })

    await act(async () => pending.resolve(sentA))
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
    const pending = deferred<ChatMessage>()
    send.mockReturnValueOnce(pending.promise)
    await renderReadyPage()
    submit(sentA.content)
    expect(send).toHaveBeenCalledExactlyOnceWith(sessionA.id, { content: sentA.content })
    select(sessionB.title)
    await screen.findByText(messageB.content)
    expect(editor().value).toBe('')
    fireEvent.change(editor(), { target: { value: 'Rascunho de B' } })

    await act(async () => pending.resolve(sentA))

    expect(screen.queryByText(sentA.content)).toBeNull()
    expect(editor().value).toBe('Rascunho de B')
    expect(editor().disabled).toBe(false)
    select(sessionA.title)
    expect(await screen.findByText(sentA.content)).toBeTruthy()
  })

  it('keeps pending sends independent across conversations', async () => {
    const pendingA = deferred<ChatMessage>()
    const pendingB = deferred<ChatMessage>()
    send.mockReturnValueOnce(pendingA.promise).mockReturnValueOnce(pendingB.promise)
    await renderReadyPage()
    submit(sentA.content)
    fireEvent.click(screen.getByRole('button', { name: 'Enviar mensagem' }))
    expect(send).toHaveBeenCalledTimes(1)
    select(sessionB.title)
    await screen.findByText(messageB.content)
    submit(sentB.content)
    expect(send).toHaveBeenNthCalledWith(2, sessionB.id, { content: sentB.content })

    await act(async () => pendingA.resolve(sentA))
    expect(editor().disabled).toBe(true)
    expect(editor().value).toBe(sentB.content)
    expect(screen.queryByText(sentA.content)).toBeNull()
    await act(async () => pendingB.resolve(sentB))
    expect(screen.getByText(sentB.content)).toBeTruthy()
    expect(editor().disabled).toBe(false)
    expect(editor().value).toBe('')
  })

  it.each([
    { order: 'send first', includesSent: false },
    { order: 'send first', includesSent: true },
    { order: 'read first', includesSent: false },
    { order: 'read first', includesSent: true },
  ])('merges a resumed read and send: $order, snapshot includes send=$includesSent', async ({ order, includesSent }) => {
    const pendingSend = deferred<ChatMessage>()
    const pendingRead = deferred<ChatSessionDetail>()
    send.mockReturnValueOnce(pendingSend.promise)
    read.mockResolvedValueOnce(detailA).mockResolvedValueOnce(detailB).mockReturnValueOnce(pendingRead.promise)
    await renderReadyPage()
    submit(sentA.content)
    select(sessionB.title)
    await screen.findByText(messageB.content)
    select(sessionA.title)
    const snapshot = { ...sessionA, messages: includesSent ? [messageA, sentA] : [messageA] }

    if (order === 'send first') {
      await act(async () => pendingSend.resolve(sentA))
      expect(screen.getByText('Carregando conversa...')).toBeTruthy()
      await act(async () => pendingRead.resolve(snapshot))
    } else {
      await act(async () => pendingRead.resolve(snapshot))
      expect(editor().disabled).toBe(true)
      await act(async () => pendingSend.resolve(sentA))
    }

    const log = screen.getByRole('log')
    expect(within(log).getAllByText(sentA.content)).toHaveLength(1)
    expect(within(log).getAllByRole('article').map((article) => article.querySelector('p')?.textContent))
      .toEqual([messageA.content, sentA.content])
    expect(editor().disabled).toBe(false)
  })

  it('preserves the draft and displays the error when the current send fails', async () => {
    const pending = deferred<ChatMessage>()
    send.mockReturnValueOnce(pending.promise)
    await renderReadyPage()
    submit(sentA.content)

    await act(async () => pending.reject(new Error('Offline')))

    expect(screen.getByRole('alert').textContent).toBe('Não foi possível enviar a mensagem.')
    expect(editor().value).toBe(sentA.content)
    expect(editor().disabled).toBe(false)
    expect(within(screen.getByRole('log')).queryByText(sentA.content)).toBeNull()
  })

  it('associates a failed send with its original conversation', async () => {
    const pending = deferred<ChatMessage>()
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
    expect(screen.getByRole('alert').textContent).toBe('Não foi possível enviar a mensagem.')
  })

  it('resets an unsent draft when switching conversations', async () => {
    await renderReadyPage()
    fireEvent.change(editor(), { target: { value: 'Rascunho de A' } })

    select(sessionB.title)
    await screen.findByText(messageB.content)

    expect(editor().value).toBe('')
    expect(send).not.toHaveBeenCalled()
  })
})
