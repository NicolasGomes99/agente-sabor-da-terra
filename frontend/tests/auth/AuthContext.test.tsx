import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { useAuth } from '../../src/features/auth/useAuth'

const { loginRequest } = vi.hoisted(() => ({
  loginRequest: vi.fn(),
}))

vi.mock('../../src/features/auth/authApi', () => ({
  login: loginRequest,
}))

function AuthConsumer() {
  const { isAuthenticated, login, logout } = useAuth()

  return (
    <>
      <span>{isAuthenticated ? 'authenticated' : 'anonymous'}</span>
      <button
        type="button"
        onClick={() => void login({ email: 'user@example.com', password: 'secret' })}
      >
        login
      </button>
      <button type="button" onClick={logout}>
        logout
      </button>
    </>
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    loginRequest.mockReset()
  })

  it('persists the token and exposes authenticated state after login', async () => {
    loginRequest.mockResolvedValue({ access_token: 'access-token' })
    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'login' }))

    expect(await screen.findByText('authenticated')).toBeTruthy()
    expect(localStorage.getItem('sabor-da-terra.access-token')).toBe(
      'access-token',
    )
  })

  it('clears the token and authenticated state on logout', async () => {
    localStorage.setItem('sabor-da-terra.access-token', 'access-token')
    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    )

    expect(screen.getByText('authenticated')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'logout' }))

    expect(screen.getByText('anonymous')).toBeTruthy()
    expect(localStorage.getItem('sabor-da-terra.access-token')).toBeNull()
  })
})
