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
import { getProducer, listProducers, listProducts } from '../../src/features/registry/registryApi'
import {
  getSolicitationSession,
  listSolicitations,
} from '../../src/features/triage/triageApi'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/documents/documentsApi', () => ({ listDocuments: vi.fn() }))
const list = vi.mocked(listDocuments)
vi.mock('../../src/features/registry/registryApi', () => ({
  getProducer: vi.fn(),
  listProducers: vi.fn(),
  listProducts: vi.fn(),
}))
const productList = vi.mocked(listProducts)
const producerList = vi.mocked(listProducers)
const producerRead = vi.mocked(getProducer)
vi.mock('../../src/features/chat/chatApi', () => ({
  createChatSession: vi.fn(),
  getChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  sendChatMessage: vi.fn(),
}))
vi.mock('../../src/features/triage/triageApi', () => ({
  finalizeSolicitation: vi.fn(),
  getSolicitationSession: vi.fn(),
  listSolicitations: vi.fn(),
  sendSolicitationMessage: vi.fn(),
}))
const chatList = vi.mocked(listChatSessions)
const chatRead = vi.mocked(getChatSession)
const chatCreate = vi.mocked(createChatSession)
const chatSend = vi.mocked(sendChatMessage)
const triageList = vi.mocked(listSolicitations)
const triageRead = vi.mocked(getSolicitationSession)
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
    productList.mockReset().mockResolvedValue([])
    producerList.mockReset().mockResolvedValue([])
    producerRead.mockReset()
    chatList.mockReset().mockResolvedValue([])
    chatRead.mockReset().mockResolvedValue({ ...session, messages: [] })
    chatCreate.mockReset().mockResolvedValue(session)
    chatSend.mockReset()
    triageList.mockReset().mockResolvedValue([])
    triageRead.mockReset()
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

  it.each(['/triagem', '/triagem/solicitation-a'])(
    'redirects unauthenticated users from triage route %s to login',
    (path) => {
      renderRoutes(path)

      expect(
        screen.getByRole('heading', { name: 'Acesso à cooperativa' }),
      ).toBeTruthy()
      expect(triageList).not.toHaveBeenCalled()
      expect(triageRead).not.toHaveBeenCalled()
    },
  )

  it('returns to login when the triage queue rejects the token', async () => {
    setAccessToken('expired-token')
    triageList.mockRejectedValueOnce(new ApiError(401, null))
    renderRoutes('/triagem')

    expect(
      await screen.findByRole('heading', { name: 'Acesso à cooperativa' }),
    ).toBeTruthy()
    expect(getAccessToken()).toBeNull()
  })

  it('returns to login when the triage detail rejects the token', async () => {
    setAccessToken('expired-token')
    triageRead.mockRejectedValueOnce(new ApiError(401, null))
    renderRoutes('/triagem/solicitation-a')

    expect(
      await screen.findByRole('heading', { name: 'Acesso à cooperativa' }),
    ).toBeTruthy()
    expect(getAccessToken()).toBeNull()
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

  it('redirects unauthenticated users from products to login', () => {
    renderRoutes('/registry/products')

    expect(screen.getByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
    expect(productList).not.toHaveBeenCalled()
  })

  it('opens products from Cadastros and returns to login on 401', async () => {
    setAccessToken('expired-token')
    list.mockResolvedValue([])
    productList.mockRejectedValueOnce(new ApiError(401, { detail: 'Unauthorized' }))
    renderRoutes('/documents')
    await screen.findByText('Nenhum documento cadastrado.')

    fireEvent.click(screen.getByRole('link', { name: 'Cadastros' }))

    expect(screen.getByRole('heading', { name: 'Produtos' })).toBeTruthy()
    expect(await screen.findByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
    expect(getAccessToken()).toBeNull()
  })

  it('redirects unauthenticated users from producers to login', () => {
    renderRoutes('/registry/producers')

    expect(screen.getByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
    expect(productList).not.toHaveBeenCalled()
    expect(producerList).not.toHaveBeenCalled()
  })

  it('switches between Products and Producers from Cadastros', async () => {
    setAccessToken('access-token')
    list.mockResolvedValue([])
    renderRoutes('/documents')
    await screen.findByText('Nenhum documento cadastrado.')

    fireEvent.click(screen.getByRole('link', { name: 'Cadastros' }))
    await screen.findByText('Nenhum produto cadastrado.')
    expect(screen.getByRole('link', { name: 'Produtos' }).getAttribute('aria-current')).toBe('page')

    fireEvent.click(screen.getByRole('link', { name: 'Produtores' }))
    await screen.findByText('Nenhum produtor cadastrado.')
    expect(screen.getByRole('link', { name: 'Cadastros' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Produtores' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Produtos' }).hasAttribute('aria-current')).toBe(false)

    fireEvent.click(screen.getByRole('link', { name: 'Produtos' }))
    await screen.findByText('Nenhum produto cadastrado.')
    expect(screen.getByRole('link', { name: 'Cadastros' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Produtos' }).getAttribute('aria-current')).toBe('page')
  })

  it.each(['catalog', 'listing'])(
    'returns to login when a producer page request rejects the token ($0)',
    async (request) => {
      setAccessToken('expired-token')
      const error = new ApiError(401, { detail: 'Unauthorized' })
      if (request === 'catalog') productList.mockRejectedValueOnce(error)
      else producerList.mockRejectedValueOnce(error)

      renderRoutes('/registry/producers')

      expect(await screen.findByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
      expect(getAccessToken()).toBeNull()
    },
  )

  it('redirects unauthenticated users from producer detail to login', () => {
    renderRoutes('/registry/producers/ana')

    expect(screen.getByRole('heading', { name: 'Acesso à cooperativa' })).toBeTruthy()
    expect(producerRead).not.toHaveBeenCalled()
  })

  it('opens producer detail and restores the list search and product filter', async () => {
    setAccessToken('access-token')
    const lettuce = { id: 'lettuce', name: 'Alface' }
    const ana = {
      id: 'ana', name: 'Ana Silva', code: 'P001', cpf: '01234567890', active: true,
      municipality: 'Caruaru', address: null, phone: null, email: null, products: [lettuce],
    }
    productList.mockResolvedValue([lettuce])
    producerList.mockResolvedValue([ana])
    producerRead.mockResolvedValueOnce(ana)
    renderRoutes('/registry/producers')
    await screen.findByRole('link', { name: ana.name })
    await screen.findByRole('option', { name: lettuce.name })

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'P001' } })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: lettuce.id } })
    fireEvent.click(await screen.findByRole('link', { name: ana.name }))

    expect(await screen.findByRole('heading', { name: ana.name })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Produtores' }).getAttribute('aria-current')).toBe('page')
    expect(producerRead).toHaveBeenCalledExactlyOnceWith(ana.id, expect.any(AbortSignal))

    fireEvent.click(screen.getByRole('link', { name: 'Voltar para produtores' }))
    expect(await screen.findByRole('link', { name: ana.name })).toBeTruthy()
    await screen.findByRole('option', { name: lettuce.name })
    expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('P001')
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe(lettuce.id)
    expect(producerList).toHaveBeenLastCalledWith(lettuce.id, expect.any(AbortSignal))
  })

  it('returns to login when the producer detail API rejects the token', async () => {
    setAccessToken('expired-token')
    producerRead.mockRejectedValueOnce(new ApiError(401, { detail: 'Unauthorized' }))
    renderRoutes('/registry/producers/ana')

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
