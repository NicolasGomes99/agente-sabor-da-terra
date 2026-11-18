import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '../../src/app/routes'
import { AuthProvider } from '../../src/features/auth/AuthContext'
import {
  createChatSession,
  getChatSession,
  listChatSessions,
  sendChatMessage,
} from '../../src/features/chat/chatApi'
import { listDocuments } from '../../src/features/documents/documentsApi'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/documents/documentsApi', () => ({ listDocuments: vi.fn() }))
const list = vi.mocked(listDocuments)
vi.mock('../../src/features/chat/chatApi', () => ({
  createChatSession: vi.fn(),
  getChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  sendChatMessage: vi.fn(),
}))
const chatList = vi.mocked(listChatSessions)
const chatRead = vi.mocked(getChatSession)
const chatCreate = vi.mocked(createChatSession)
const chatSend = vi.mocked(sendChatMessage)
const session = { id: 'session-a', title: 'Conversa A', created_at: '2026-11-17T12:00:00Z' }

function renderRoutes(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('AppRoutes', () => {
  beforeEach(() => {
    localStorage.clear()
    list.mockReset()
    chatList.mockReset().mockResolvedValue([])
    chatRead.mockReset().mockResolvedValue({ ...session, messages: [] })
    chatCreate.mockReset().mockResolvedValue(session)
    chatSend.mockReset()
  })

  it('redirects unauthenticated users from chat to login', () => {
    renderRoutes('/chat')

    expect(
      screen.getByRole('heading', { name: 'Acesso à cooperativa' }),
    ).toBeTruthy()
  })

  it('redirects authenticated users from login to chat', async () => {
    localStorage.setItem('sabor-da-terra.access-token', 'access-token')
    renderRoutes('/login')

    expect(screen.getByRole('heading', { name: 'Novo chat' })).toBeTruthy()
    expect(await screen.findByRole('log')).toBeTruthy()
  })

  it('redirects unauthenticated users from documents to login', () => {
    renderRoutes('/documents')

    expect(screen.getByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
    expect(list).not.toHaveBeenCalled()
  })

  it('renders documents for an authenticated user', async () => {
    setAccessToken('access-token')
    list.mockResolvedValue([{ id: 'first', original_filename: 'Ata.pdf' }])
    renderRoutes('/documents')

    expect(screen.getByRole('heading', { name: 'Documentos' })).toBeTruthy()
    expect(await screen.findByText('Ata.pdf')).toBeTruthy()
  })

  it('returns to login when the documents API rejects the token', async () => {
    setAccessToken('expired-token')
    list.mockRejectedValue(new ApiError(401, { detail: 'Unauthorized' }))
    renderRoutes('/documents')

    expect(await screen.findByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
    expect(getAccessToken()).toBeNull()
  })

  it.each(['list', 'read', 'create', 'send'])(
    'returns to login when chat %s rejects the token', async (operation) => {
      setAccessToken('expired-token')
      const error = new ApiError(401, { detail: 'Unauthorized' })
      chatList.mockResolvedValue([session])
      if (operation === 'list') chatList.mockRejectedValueOnce(error)
      if (operation === 'read') chatRead.mockRejectedValueOnce(error)
      if (operation === 'create') chatCreate.mockRejectedValueOnce(error)
      if (operation === 'send') chatSend.mockRejectedValueOnce(error)
      renderRoutes('/chat')

      if (operation === 'create' || operation === 'send') {
        await screen.findByRole('log')
        if (operation === 'create') {
          fireEvent.click(screen.getByRole('button', { name: '+ Nova conversa' }))
        } else {
          fireEvent.change(screen.getByRole('textbox', { name: 'Mensagem para o assistente' }), {
            target: { value: 'Olá' },
          })
          fireEvent.click(screen.getByRole('button', { name: 'Enviar mensagem' }))
        }
      }

      expect(await screen.findByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
      expect(getAccessToken()).toBeNull()
    },
  )
})
