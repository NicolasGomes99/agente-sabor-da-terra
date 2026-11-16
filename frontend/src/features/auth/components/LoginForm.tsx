import { useState, type FormEvent } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../useAuth'
import type { LoginCredentials } from '../types'

interface LoginFormProps {
  onSuccess?: () => void
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return 'E-mail ou senha inválidos.'
  }

  return 'Não foi possível entrar. Tente novamente.'
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const { login } = useAuth()
  const [credentials, setCredentials] = useState<LoginCredentials>({
    email: '',
    password: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  function updateField(field: keyof LoginCredentials, value: string): void {
    setCredentials((current) => ({ ...current, [field]: value }))
    setError(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      await login(credentials)
      onSuccess?.()
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <div className="login-field">
        <label htmlFor="login-email">E-mail</label>
        <input
          id="login-email"
          name="email"
          type="email"
          autoComplete="email"
          value={credentials.email}
          onChange={(event) => updateField('email', event.target.value)}
          required
          disabled={isSubmitting}
        />
      </div>

      <div className="login-field">
        <label htmlFor="login-password">Senha</label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={credentials.password}
          onChange={(event) => updateField('password', event.target.value)}
          required
          disabled={isSubmitting}
        />
      </div>

      {error && (
        <p className="login-error" role="alert">
          {error}
        </p>
      )}

      <button className="login-submit" type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Entrando...' : 'Entrar'}
      </button>
    </form>
  )
}
