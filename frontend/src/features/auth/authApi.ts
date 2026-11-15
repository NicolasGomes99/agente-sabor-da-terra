import { apiRequest } from '../../lib/api-client'
import type { LoginCredentials, LoginResponse } from './types'

export function login(
  credentials: LoginCredentials,
): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}
