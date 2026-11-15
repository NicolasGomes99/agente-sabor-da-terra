import {
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { login as loginRequest } from './authApi'
import { AuthContext } from './auth-context'
import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from '../../lib/auth-storage'
import type { AuthContextValue } from './auth-context'
import type { LoginCredentials } from './types'

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [accessToken, setAccessTokenState] = useState<string | null>(
    getAccessToken,
  )

  async function login(credentials: LoginCredentials): Promise<void> {
    const response = await loginRequest(credentials)
    setAccessToken(response.access_token)
    setAccessTokenState(response.access_token)
  }

  function logout(): void {
    clearAccessToken()
    setAccessTokenState(null)
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken,
      isAuthenticated: accessToken !== null,
      login,
      logout,
    }),
    [accessToken],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
