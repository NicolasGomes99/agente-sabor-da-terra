import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AppRoutes } from '../../src/app/routes'
import { AuthProvider } from '../../src/features/auth/AuthContext'

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
})
