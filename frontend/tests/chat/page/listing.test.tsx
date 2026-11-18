import { act, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  deferred, editor, list, messageA, read, renderPage, sessionA, sessionB,
  setupChatPageTests,
} from './helpers'

describe('ChatPage listing', () => {
  setupChatPageTests()

  it('loads sessions and selects the first conversation', async () => {
    const pending = deferred<typeof sessionA[]>()
    list.mockReturnValueOnce(pending.promise)
    renderPage()

    expect(screen.getByText('Carregando conversa...')).toBeTruthy()
    expect(editor().disabled).toBe(true)
    await act(async () => pending.resolve([sessionA, sessionB]))

    expect(screen.getByRole('heading', { name: sessionA.title })).toBeTruthy()
    expect(screen.getByText(messageA.content)).toBeTruthy()
    expect(read).toHaveBeenCalledExactlyOnceWith(sessionA.id, expect.any(AbortSignal))
    expect(editor().disabled).toBe(false)
  })

  it('shows an empty history when there are no sessions', async () => {
    list.mockResolvedValueOnce([])
    renderPage()

    const log = await screen.findByRole('log')
    expect(within(log).queryAllByRole('article')).toHaveLength(0)
    expect(editor().disabled).toBe(true)
    expect(read).not.toHaveBeenCalled()
  })

  it('shows the error of a current list request', async () => {
    list.mockRejectedValueOnce(new Error('Offline'))
    renderPage()

    expect((await screen.findByRole('alert')).textContent).toBe('Não foi possível carregar as conversas.')
    expect(screen.queryByText('Carregando conversa...')).toBeNull()
  })
})
