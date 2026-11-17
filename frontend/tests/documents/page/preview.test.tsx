import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../../src/features/auth/AuthContext'
import { getDocumentContent, listDocuments } from '../../../src/features/documents/documentsApi'
import { DocumentsPage } from '../../../src/features/documents/pages/DocumentsPage'
import { ApiError } from '../../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../../src/lib/auth-storage'

vi.mock('../../../src/features/documents/documentsApi', () => ({
  listDocuments: vi.fn(),
  getDocumentContent: vi.fn(),
}))

const list = vi.mocked(listDocuments)
const content = vi.mocked(getDocumentContent)
const createObjectURL = vi.fn(() => 'blob:preview')
const revokeObjectURL = vi.fn()

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><DocumentsPage /></AuthProvider>
    </MemoryRouter>,
  )
}

async function openDocument(filename: string) {
  const row = await screen.findByText(filename)
  const item = row.closest('li')
  if (!item) throw new Error('Document row not found')
  fireEvent.click(within(item).getByRole('button', { name: 'Abrir' }))
}

describe('DocumentsPage preview', () => {
  beforeEach(() => {
    localStorage.clear()
    list.mockReset()
    content.mockReset()
    createObjectURL.mockClear()
    revokeObjectURL.mockClear()
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL }))
  })

  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('shows Open only for supported formats', async () => {
    const supported = ['Ata.PDF', 'Foto.gif', 'Foto.jpg', 'Foto.jpeg', 'Foto.png', 'Foto.webp',
      'Notas.txt', 'Notas.md', 'Dados.csv', 'Dados.json']
    const unsupported = ['Arquivo.zip', 'Arquivo.html', 'Arquivo.pdf.gz', 'pdf']
    list.mockResolvedValue([...supported, ...unsupported].map((name) => ({
      id: name, original_filename: name,
    })))
    renderPage()

    const rows = await screen.findAllByRole('listitem')
    expect(rows).toHaveLength(supported.length + unsupported.length)
    for (const [index, row] of rows.entries()) {
      expect(Boolean(within(row).queryByRole('button', { name: 'Abrir' })))
        .toBe(index < supported.length)
    }
  })

  it.each([
    ['Ata.pdf', 'application/pdf'],
    ['Foto.webp', 'image/webp'],
  ])('renders and releases the media preview for %s', async (filename, mime) => {
    list.mockResolvedValue([{ id: 'first', original_filename: filename }])
    const blob = new Blob(['content'], { type: mime })
    content.mockResolvedValue(blob)
    renderPage()
    await openDocument(filename)

    const viewer = mime === 'application/pdf'
      ? await screen.findByTitle(filename)
      : await screen.findByRole('img', { name: filename })
    const signal = content.mock.calls[0][1]
    expect(content).toHaveBeenCalledExactlyOnceWith('first', signal)
    expect(signal?.aborted).toBe(false)
    expect(viewer.getAttribute('src')).toBe('blob:preview')
    expect(createObjectURL).toHaveBeenCalledExactlyOnceWith(blob)

    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(signal?.aborted).toBe(true)
    expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:preview')
    expect(viewer.isConnected).toBe(false)
  })

  it('rejects an incompatible MIME for a media preview', async () => {
    list.mockResolvedValue([{ id: 'first', original_filename: 'Ata.pdf' }])
    content.mockResolvedValue(new Blob(['content'], { type: 'application/octet-stream' }))
    renderPage()
    await openDocument('Ata.pdf')

    expect((await screen.findByRole('alert')).textContent)
      .toBe('Este formato não pode ser visualizado.')
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it.each(['txt', 'md', 'csv', 'json'])('renders %s as literal text', async (extension) => {
    const filename = `Notas.${extension}`
    const text = '<strong>Texto de exemplo</strong>'
    list.mockResolvedValue([{ id: 'first', original_filename: filename }])
    content.mockResolvedValue(await new Response(text, {
      headers: { 'Content-Type': 'application/octet-stream' },
    }).blob())
    renderPage()
    await openDocument(filename)

    const literal = await screen.findByText(text, { selector: 'pre' })
    expect(literal.querySelector('strong')).toBeNull()
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it('ignores a stale preview when switching documents', async () => {
    list.mockResolvedValue([
      { id: 'first', original_filename: 'Ata.pdf' },
      { id: 'second', original_filename: 'Foto.png' },
    ])
    let resolveFirst!: (value: Blob) => void
    content.mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce(new Blob(['image'], { type: 'image/png' }))
    const { unmount } = renderPage()
    await openDocument('Ata.pdf')
    expect(screen.getByText('Abrindo documento…')).toBeTruthy()
    const firstSignal = content.mock.calls[0][1]

    await openDocument('Foto.png')
    expect(firstSignal?.aborted).toBe(true)
    const image = await screen.findByRole('img', { name: 'Foto.png' })

    await act(async () => resolveFirst(new Blob(['pdf'], { type: 'application/pdf' })))
    expect(image.isConnected).toBe(true)
    expect(screen.queryByTitle('Ata.pdf')).toBeNull()
    expect(createObjectURL).toHaveBeenCalledOnce()

    const secondSignal = content.mock.calls[1][1]
    unmount()
    expect(secondSignal?.aborted).toBe(true)
    expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:preview')
  })

  it.each([
    [new ApiError(404, null), 'O documento está indisponível.'],
    [new Error('Network error'), 'Não foi possível abrir o documento.'],
  ])('shows preview errors: %s', async (error, message) => {
    list.mockResolvedValue([{ id: 'first', original_filename: 'Ata.pdf' }])
    content.mockRejectedValue(error)
    renderPage()
    await openDocument('Ata.pdf')

    expect((await screen.findByRole('alert')).textContent).toBe(message)
  })

  it('logs out when the preview returns 401', async () => {
    setAccessToken('expired-token')
    list.mockResolvedValue([{ id: 'first', original_filename: 'Ata.pdf' }])
    content.mockRejectedValue(new ApiError(401, null))
    renderPage()
    await openDocument('Ata.pdf')

    await waitFor(() => expect(getAccessToken()).toBeNull())
  })
})
