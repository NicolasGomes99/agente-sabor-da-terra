export interface LoginCredentials {
  email: string
  password: string
}

export type TokenType = 'bearer'

export interface LoginResponse {
  access_token: string
  token_type: TokenType
}

export interface AuthState {
  accessToken: string | null
  isAuthenticated: boolean
}
