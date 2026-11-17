import { act, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ChatSessionDetail } from '../../../src/features/chat/types'
import { ApiError } from '../../../src/lib/api-client'
import { getAccessToken } from '../../../src/lib/auth-storage'
import {
  deferred, detailA, detailB, editor, messageA, messageB, read, renderPage,
  select, sessionA, sessionB, setupChatPageTests,
} from './helpers'

describe('ChatPage selection', () => {
  setupChatPageTests()

  it('keeps B selected when the canceled read of A resolves last', async () => {
    const pendingA = deferred<ChatSessionDetail>()
    read.mockReturnValueOnce(pendingA.promise)
    renderPage()
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1))
    const signalA = read.mock.calls[0][1]

    select(sessionB.title)
    await screen.findByText(messageB.content)
    expect(signalA?.aborted).toBe(true)
    await act(async () => pendingA.resolve(detailA))

    expect(screen.getByRole('heading', { name: sessionB.title })).toBeTruthy()
    expect(screen.getByText(messageB.content)).toBeTruthy()
    expect(screen.queryByText(messageA.content)).toBeNull()
    expect(editor().disabled).toBe(false)
  })

  it('distinguishes two reads of A after selecting A, B, and A', async () => {
    const firstA = deferred<ChatSessionDetail>()
    const lastA = deferred<ChatSessionDetail>()
    read.mockReturnValueOnce(firstA.promise)
      .mockResolvedValueOnce(detailB)
      .mockReturnValueOnce(lastA.promise)
    renderPage()
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1))
    select(sessionB.title)
    await screen.findByText(messageB.content)
    select(sessionA.title)
    const updatedMessage = { ...messageA, content: 'Mensagem atualizada de A' }

    await act(async () => lastA.resolve({ ...sessionA, messages: [updatedMessage] }))
    await act(async () => firstA.resolve(detailA))

    expect(screen.getByText(updatedMessage.content)).toBeTruthy()
    expect(screen.queryByText(messageA.content)).toBeNull()
  })

  it.each(['success', 'failure', 'unauthorized'])(
    'ignores stale read %s without ending the current loading state', async (outcome) => {
      const pendingA = deferred<ChatSessionDetail>()
      const pendingB = deferred<ChatSessionDetail>()
      read.mockReturnValueOnce(pendingA.promise).mockReturnValueOnce(pendingB.promise)
      renderPage()
      await waitFor(() => expect(read).toHaveBeenCalledTimes(1))
      select(sessionB.title)

      await act(async () => {
        if (outcome === 'success') pendingA.resolve(detailA)
        else pendingA.reject(outcome === 'unauthorized' ? new ApiError(401, null) : new Error('Offline'))
      })

      expect(screen.getByText('Carregando conversa...')).toBeTruthy()
      expect(screen.queryByRole('alert')).toBeNull()
      expect(editor().disabled).toBe(true)
      expect(getAccessToken()).toBe('test-token')
      await act(async () => pendingB.resolve(detailB))
      expect(screen.getByText(messageB.content)).toBeTruthy()
      expect(editor().disabled).toBe(false)
    },
  )

  it('shows the error of a current read request', async () => {
    read.mockRejectedValueOnce(new Error('Offline'))
    renderPage()

    expect((await screen.findByRole('alert')).textContent).toBe('Não foi possível carregar as mensagens.')
    expect(screen.queryByText('Carregando conversa...')).toBeNull()
  })
})
