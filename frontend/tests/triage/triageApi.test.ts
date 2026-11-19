import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  finalizeSolicitation,
  getSolicitation,
  getSolicitationSession,
  listSolicitations,
  sendSolicitationMessage,
} from '../../src/features/triage/triageApi'
import { ApiError } from '../../src/lib/api-client'
import { clearAccessToken, setAccessToken } from '../../src/lib/auth-storage'

const timestamp = '2026-10-30T12:00:00Z'
const solicitation = {
  id: 'solicitation/a',
  session_id: 'session-a',
  summary: 'Pedido de tomate.',
  request_type: 'pedido',
  urgency: 'urgente',
  status: 'recebida',
}
const message = {
  id: 'message-a',
  role: 'user',
  content: 'Olá',
  position: 1,
  created_at: timestamp,
}
const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const fetchMock = vi.fn<typeof fetch>()

function authorization() {
  return new Headers(fetchMock.mock.calls[0][1]?.headers).get(
    'Authorization',
  )
}

describe('triage API', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('test-token')
  })

  afterEach(() => {
    clearAccessToken()
    vi.unstubAllGlobals()
  })

  it('lists solicitations with authentication and cancellation', async () => {
    const { signal } = new AbortController()
    fetchMock.mockResolvedValueOnce(Response.json([solicitation]))

    await expect(listSolicitations(signal)).resolves.toEqual([solicitation])

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/solicitations`,
      expect.objectContaining({ signal }),
    )
    expect(authorization()).toBe('Bearer test-token')
  })

  it('loads a solicitation by its encoded identifier', async () => {
    const { signal } = new AbortController()
    fetchMock.mockResolvedValueOnce(Response.json(solicitation))

    await expect(
      getSolicitation(solicitation.id, signal),
    ).resolves.toEqual(solicitation)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/solicitations/solicitation%2Fa`,
      expect.objectContaining({ signal }),
    )
    expect(authorization()).toBe('Bearer test-token')
  })

  it('opens the solicitation session with authentication and cancellation', async () => {
    const { signal } = new AbortController()
    const detail = {
      ...solicitation,
      title: 'PED-2026-015',
      created_at: timestamp,
      read_only: false,
      messages: [message],
    }
    fetchMock.mockResolvedValueOnce(Response.json(detail))

    await expect(
      getSolicitationSession(solicitation.id, signal),
    ).resolves.toEqual(detail)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/solicitations/solicitation%2Fa/session`,
      expect.objectContaining({ signal }),
    )
    expect(authorization()).toBe('Bearer test-token')
  })

  it('sends a clarification as authenticated JSON', async () => {
    fetchMock.mockResolvedValueOnce(Response.json(message, { status: 201 }))

    await expect(
      sendSolicitationMessage(solicitation.id, { content: message.content }),
    ).resolves.toEqual(message)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/solicitations/solicitation%2Fa/messages`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: message.content }),
      }),
    )
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers)
    expect(headers.get('Authorization')).toBe('Bearer test-token')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('finalizes a solicitation with an authenticated POST', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({
      ...solicitation,
      status: 'finalizada',
    }))

    await expect(
      finalizeSolicitation(solicitation.id),
    ).resolves.toMatchObject({ status: 'finalizada' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/solicitations/solicitation%2Fa/finalize`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(authorization()).toBe('Bearer test-token')
  })

  it.each([
    { operation: 'list', request: () => listSolicitations() },
    { operation: 'read', request: () => getSolicitation(solicitation.id) },
    {
      operation: 'open session',
      request: () => getSolicitationSession(solicitation.id),
    },
    {
      operation: 'send',
      request: () => sendSolicitationMessage(solicitation.id, { content: 'Oi' }),
    },
    {
      operation: 'finalize',
      request: () => finalizeSolicitation(solicitation.id),
    },
  ])('preserves API errors from $operation', async ({ request }) => {
    const details = { detail: 'Unauthorized' }
    fetchMock.mockResolvedValueOnce(Response.json(details, { status: 401 }))

    const result = request()

    await expect(result).rejects.toBeInstanceOf(ApiError)
    await expect(result).rejects.toMatchObject({ status: 401, details })
  })
})
