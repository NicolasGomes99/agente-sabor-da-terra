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

async function fetchApi(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
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

  if (!response.ok) {
    throw new ApiError(response.status, await readResponseBody(response))
  }

  return response
}

async function readResponseBody(response: Response): Promise<unknown> {
  const responseText = await response.text()
  let details: unknown

  if (responseText) {
    try {
      details = JSON.parse(responseText)
    } catch {
      details = responseText
    }
  }

  return details
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  return (await readResponseBody(await fetchApi(path, options))) as T
}

export async function apiRequestBlob(
  path: string,
  options: RequestInit = {},
): Promise<Blob> {
  const response = await fetchApi(path, options)
  return response.blob()
}
