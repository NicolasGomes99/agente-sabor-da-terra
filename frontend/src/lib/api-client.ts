import { getAccessToken } from './auth-storage'

const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  readonly details: unknown

  constructor(status: number, details: unknown) {
    super(`API request failed with status ${status}.`)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  const accessToken = getAccessToken()

  if (
    typeof options.body === 'string' &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json')
  }

  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  const responseText = await response.text()
  let details: unknown

  if (responseText) {
    try {
      details = JSON.parse(responseText)
    } catch {
      details = responseText
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, details)
  }

  return details as T
}
