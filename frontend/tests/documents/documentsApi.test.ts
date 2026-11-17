import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  deleteDocument,
  downloadDocument,
  getDocumentContent,
  listDocuments,
  uploadDocument,
} from '../../src/features/documents/documentsApi'
import { ApiError } from '../../src/lib/api-client'
import { clearAccessToken, setAccessToken } from '../../src/lib/auth-storage'

const record = { id: 'document-id', original_filename: 'Certidão.pdf' }
const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const fetchMock = vi.fn<typeof fetch>()

describe('documents API', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('test-token')
  })

  afterEach(() => {
    clearAccessToken()
    vi.unstubAllGlobals()
  })

  it('lists documents with the bearer token', async () => {
    const { signal } = new AbortController()
    fetchMock.mockResolvedValueOnce(Response.json([record]))

    await expect(listDocuments(signal)).resolves.toEqual([record])

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/documents`,
      expect.objectContaining({ signal }),
    )
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization'))
      .toBe('Bearer test-token')
  })

  it('uploads a file as multipart form data', async () => {
    const file = new File(['document'], record.original_filename, { type: 'application/pdf' })
    fetchMock.mockResolvedValueOnce(Response.json(record, { status: 201 }))

    await expect(uploadDocument(file)).resolves.toEqual(record)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/documents`,
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
    const options = fetchMock.mock.calls[0][1]
    const body = options?.body as FormData | undefined
    expect(body?.get('file')).toBe(file)
    const headers = new Headers(options?.headers)
    expect(headers.get('Authorization')).toBe('Bearer test-token')
    expect(headers.has('Content-Type')).toBe(false)
  })

  it.each([
    { endpoint: 'content', request: getDocumentContent },
    { endpoint: 'download', request: downloadDocument },
  ])('returns an authenticated blob from $endpoint', async ({ endpoint, request }) => {
    const bytes = Uint8Array.of(0, 128, 255)
    const { signal } = new AbortController()
    fetchMock.mockResolvedValueOnce(new Response(bytes, {
      headers: { 'Content-Type': 'application/pdf' },
    }))

    const blob = await request(record.id, signal)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/documents/${record.id}/${endpoint}`,
      expect.anything(),
    )
    const options = fetchMock.mock.calls[0][1]
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer test-token')
    if (endpoint === 'content') {
      expect(options?.signal).toBe(signal)
    }
    expect(blob.type).toBe('application/pdf')
    expect(new Uint8Array(await blob.arrayBuffer())).toEqual(bytes)
  })

  it('deletes a document with an empty response', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))

    await expect(deleteDocument(record.id)).resolves.toBeUndefined()

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${baseUrl}/documents/${record.id}`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization'))
      .toBe('Bearer test-token')
  })

  it('preserves error details for a binary request', async () => {
    const details = { detail: 'Document not found.' }
    fetchMock.mockResolvedValueOnce(Response.json(details, { status: 404 }))

    const result = getDocumentContent(record.id)

    await expect(result).rejects.toBeInstanceOf(ApiError)
    await expect(result).rejects.toMatchObject({ status: 404, details })
  })
})
