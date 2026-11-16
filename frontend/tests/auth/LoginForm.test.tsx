import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { LoginForm } from '../../src/features/auth/components/LoginForm'
import { ApiError } from '../../src/lib/api-client'

const { loginRequest } = vi.hoisted(() => ({
  loginRequest: vi.fn(),
}))

vi.mock('../../src/features/auth/authApi', () => ({
  login: loginRequest,
}))

function renderLoginForm(onSuccess = vi.fn()) {
  return render(
    <AuthProvider>
      <LoginForm onSuccess={onSuccess} />
    </AuthProvider>,
  )
}

describe('LoginForm', () => {
  beforeEach(() => {
    localStorage.clear()
    loginRequest.mockReset()
  })

  it('submits credentials, persists login, and calls onSuccess', async () => {
    loginRequest.mockResolvedValue({ access_token: 'access-token' })
    const onSuccess = vi.fn()
    renderLoginForm(onSuccess)

    fireEvent.change(screen.getByLabelText('E-mail'), {
      target: { value: 'user@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Senha'), {
      target: { value: 'secret' },
    })
    fireEvent.submit(screen.getByRole('button', { name: 'Entrar' }).closest('form')!)

    const submitButton = await screen.findByRole('button', { name: 'Entrar' })
    expect(submitButton).toBeTruthy()
    expect((submitButton as HTMLButtonElement).disabled).toBe(false)
    expect(loginRequest).toHaveBeenCalledWith({
      email: 'user@example.com',
      password: 'secret',
    })
    expect(onSuccess).toHaveBeenCalledOnce()
  })

  it('shows an invalid credentials message for an unauthorized response', async () => {
    loginRequest.mockRejectedValue(new ApiError(401, { detail: 'Invalid credentials.' }))
    renderLoginForm()

    fireEvent.change(screen.getByLabelText('E-mail'), {
      target: { value: 'user@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Senha'), {
      target: { value: 'wrong' },
    })
    fireEvent.submit(screen.getByRole('button', { name: 'Entrar' }).closest('form')!)

    expect((await screen.findByRole('alert')).textContent).toContain(
      'E-mail ou senha inválidos.',
    )
  })
})
