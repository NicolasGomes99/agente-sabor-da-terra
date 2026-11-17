import { act, fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  create, deferred, editor, list, messageB, read, renderPage, renderReadyPage,
  select, sessionA, sessionB, sessionC, setupChatPageTests,
} from './helpers'

describe('ChatPage creation', () => {
  setupChatPageTests()

  it.each(['before', 'after'])(
    'preserves the created session when the initial list resolves %s creation', async (order) => {
      const pendingList = deferred<typeof sessionA[]>()
      const pendingCreate = deferred<typeof sessionC>()
      list.mockReturnValueOnce(pendingList.promise)
      create.mockReturnValueOnce(pendingCreate.promise)
      renderPage()
      fireEvent.click(screen.getByRole('button', { name: '+ Nova conversa' }))

      if (order === 'before') await act(async () => pendingList.resolve([sessionA, sessionC]))
      await act(async () => pendingCreate.resolve(sessionC))
      if (order === 'after') await act(async () => pendingList.resolve([sessionA, sessionC]))

      expect(screen.getByRole('heading', { name: sessionC.title })).toBeTruthy()
      expect(screen.getAllByRole('button', { name: sessionC.title })).toHaveLength(1)
      expect(screen.getByRole('button', { name: sessionA.title })).toBeTruthy()
      expect(within(screen.getByRole('log')).queryAllByRole('article')).toHaveLength(0)
      expect(read).not.toHaveBeenCalled()
      expect(editor().disabled).toBe(false)
    },
  )

  it('ignores an initial list failure after creating a conversation', async () => {
    const pendingList = deferred<typeof sessionA[]>()
    list.mockReturnValueOnce(pendingList.promise)
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '+ Nova conversa' }))
    await screen.findByRole('heading', { name: sessionC.title })

    await act(async () => pendingList.reject(new Error('Offline')))

    expect(screen.queryByRole('alert')).toBeNull()
    expect(editor().disabled).toBe(false)
  })

  it.each(['success', 'failure'])(
    'keeps a later selection when creation ends with %s', async (outcome) => {
      const pending = deferred<typeof sessionC>()
      create.mockReturnValueOnce(pending.promise)
      await renderReadyPage()
      fireEvent.click(screen.getByRole('button', { name: '+ Nova conversa' }))
      select(sessionB.title)
      await screen.findByText(messageB.content)

      await act(async () => {
        if (outcome === 'success') pending.resolve(sessionC)
        else pending.reject(new Error('Offline'))
      })

      expect(screen.getByRole('heading', { name: sessionB.title })).toBeTruthy()
      expect(screen.getByText(messageB.content)).toBeTruthy()
      expect(screen.queryByRole('alert')).toBeNull()
      expect((screen.getByRole('button', { name: '+ Nova conversa' }) as HTMLButtonElement).disabled).toBe(false)
      if (outcome === 'success') expect(screen.getByRole('button', { name: sessionC.title })).toBeTruthy()
    },
  )

  it('blocks duplicate creation while a request is pending', async () => {
    const pending = deferred<typeof sessionC>()
    create.mockReturnValueOnce(pending.promise)
    await renderReadyPage()
    const button = screen.getByRole('button', { name: '+ Nova conversa' }) as HTMLButtonElement

    fireEvent.click(button)
    fireEvent.click(button)

    expect(button.disabled).toBe(true)
    expect(create).toHaveBeenCalledTimes(1)
    await act(async () => pending.resolve(sessionC))
    expect(button.disabled).toBe(false)
  })

  it('shows the error of a current create request', async () => {
    create.mockRejectedValueOnce(new Error('Offline'))
    await renderReadyPage()
    fireEvent.click(screen.getByRole('button', { name: '+ Nova conversa' }))

    expect((await screen.findByRole('alert')).textContent).toBe('Não foi possível criar uma nova conversa.')
    expect(screen.queryByText('Carregando conversa...')).toBeNull()
  })
})
