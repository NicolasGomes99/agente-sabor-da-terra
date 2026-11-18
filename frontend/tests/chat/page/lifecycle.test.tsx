import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ApiError } from '../../../src/lib/api-client'
import { getAccessToken } from '../../../src/lib/auth-storage'
import {
  create, deferred, list, messageA, read, renderPage, send, sentA,
  setupChatPageTests, submit,
} from './helpers'

describe('ChatPage lifecycle', () => {
  setupChatPageTests()

  it.each(['list', 'read', 'create', 'send'])(
    'ignores a late 401 from %s after unmounting', async (operation) => {
      const pending = deferred<never>()
      if (operation === 'list') list.mockReturnValueOnce(pending.promise)
      if (operation === 'read') read.mockReturnValueOnce(pending.promise)
      if (operation === 'create') create.mockReturnValueOnce(pending.promise)
      if (operation === 'send') send.mockReturnValueOnce(pending.promise)
      const { unmount } = renderPage()
      if (operation === 'read') await waitFor(() => expect(read).toHaveBeenCalledTimes(1))
      if (operation === 'create' || operation === 'send') {
        await screen.findByText(messageA.content)
        if (operation === 'create') fireEvent.click(screen.getByRole('button', { name: '+ Nova conversa' }))
        else submit(sentA.content)
      }
      const listSignal = list.mock.calls[0][0]
      const readSignal = read.mock.calls.at(-1)?.[1]
      expect(listSignal?.aborted).toBe(false)
      if (operation === 'read') expect(readSignal?.aborted).toBe(false)

      unmount()

      expect(listSignal?.aborted).toBe(true)
      if (operation === 'read') expect(readSignal?.aborted).toBe(true)
      await act(async () => pending.reject(new ApiError(401, null)))
      expect(getAccessToken()).toBe('test-token')
    },
  )
})
