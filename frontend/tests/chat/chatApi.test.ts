import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createChatSession,
  getChatSession,
  listChatSessions,
  sendChatMessage,
} from '../../src/features/chat/chatApi'
import { ApiError } from '../../src/lib/api-client'
import { clearAccessToken, setAccessToken } from '../../src/lib/auth-storage'

const session = { id: 'session-a', title: 'Conversa A', created_at: '2026-11-17T12:00:00Z' }
const message = { id: 'message-a', role: 'user', content: 'Olá', created_at: session.created_at }
const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const fetchMock = vi.fn<typeof fetch>()

describe('chat API', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('test-token')
  })

  afterEach(() => {
    clearAccessToken()
    vi.unstubAllGlobals()
  })

  it('lists sessions with authentication and cancellation', async () => {
    const { signal } = new AbortController()
    fetchMock.mockResolvedValueOnce(Response.json([session]))

    await expect(listChatSessions(signal)).resolves.toEqual([session])

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/chat/sessions`, expect.objectContaining({ signal }),
    )
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization'))
      .toBe('Bearer test-token')
  })

  it('loads a session with authentication and cancellation', async () => {
    const { signal } = new AbortController()
    const detail = { ...session, messages: [message] }
    fetchMock.mockResolvedValueOnce(Response.json(detail))

    await expect(getChatSession(session.id, signal)).resolves.toEqual(detail)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/chat/sessions/${session.id}`, expect.objectContaining({ signal }),
    )
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization'))
      .toBe('Bearer test-token')
  })

  it('creates an authenticated session', async () => {
    fetchMock.mockResolvedValueOnce(Response.json(session, { status: 201 }))

    await expect(createChatSession()).resolves.toEqual(session)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/chat/sessions`, expect.objectContaining({ method: 'POST' }),
    )
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization'))
      .toBe('Bearer test-token')
  })

  it('sends a message to the requested session', async () => {
    fetchMock.mockResolvedValueOnce(Response.json(message, { status: 201 }))

    await expect(sendChatMessage(session.id, { content: message.content })).resolves.toEqual(message)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/chat/sessions/${session.id}/messages`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ content: message.content }) }),
    )
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers)
    expect(headers.get('Authorization')).toBe('Bearer test-token')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it.each([
    { operation: 'list', request: () => listChatSessions() },
    { operation: 'read', request: () => getChatSession(session.id) },
    { operation: 'create', request: () => createChatSession() },
    { operation: 'send', request: () => sendChatMessage(session.id, { content: 'Olá' }) },
  ])('preserves API errors from $operation', async ({ request }) => {
    const details = { detail: 'Unauthorized' }
    fetchMock.mockResolvedValueOnce(Response.json(details, { status: 401 }))

    const result = request()

    await expect(result).rejects.toBeInstanceOf(ApiError)
    await expect(result).rejects.toMatchObject({ status: 401, details })
  })
})
