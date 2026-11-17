import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '../../src/app/routes'
import { AuthProvider } from '../../src/features/auth/AuthContext'
import { listDocuments } from '../../src/features/documents/documentsApi'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/documents/documentsApi', () => ({ listDocuments: vi.fn() }))
const list = vi.mocked(listDocuments)

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
  })

  it('redirects unauthenticated users from chat to login', () => {
    renderRoutes('/chat')

    expect(
      screen.getByRole('heading', { name: 'Acesso à cooperativa' }),
    ).toBeTruthy()
  })

  it('redirects authenticated users from login to chat', () => {
    localStorage.setItem('sabor-da-terra.access-token', 'access-token')
    renderRoutes('/login')

    expect(screen.getByRole('heading', { name: 'Novo chat' })).toBeTruthy()
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
})
