import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { listDocuments, uploadDocument } from '../../src/features/documents/documentsApi'
import { DocumentsPage } from '../../src/features/documents/pages/DocumentsPage'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/documents/documentsApi', () => ({
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
}))
const list = vi.mocked(listDocuments)
const upload = vi.mocked(uploadDocument)
const uploadedRecord = { id: 'new', original_filename: 'Ata.pdf' }

function pendingUpload() {
  let resolve!: (record: typeof uploadedRecord) => void
  const promise = new Promise<typeof uploadedRecord>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

function selectFile() {
  const input = screen.getByLabelText<HTMLInputElement>('Arquivo')
  const file = new File(['document'], uploadedRecord.original_filename)
  fireEvent.change(input, { target: { files: [file] } })
  return { input, file }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><DocumentsPage /></AuthProvider>
    </MemoryRouter>,
  )
}

describe('DocumentsPage', () => {
  beforeEach(() => {
    localStorage.clear()
    list.mockReset()
    upload.mockReset()
  })

  it('keeps upload disabled until the list is ready and a file is selected', async () => {
    list.mockResolvedValue([])
    renderPage()
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Enviar' })

    expect(button.disabled).toBe(true)
    selectFile()
    expect(button.disabled).toBe(true)
    await screen.findByText('Nenhum documento cadastrado.')
    expect(button.disabled).toBe(false)

    fireEvent.change(screen.getByLabelText('Arquivo'), { target: { files: [] } })
    expect(button.disabled).toBe(true)
  })

  it('adds the uploaded document only after success', async () => {
    const response = pendingUpload()
    list.mockResolvedValue([{ id: 'existing', original_filename: 'Ata.pdf' }])
    upload.mockReturnValue(response.promise)
    renderPage()
    await screen.findByText('Ata.pdf')
    const { input, file } = selectFile()

    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(upload).toHaveBeenCalledExactlyOnceWith(file)
    expect(screen.getAllByText('Ata.pdf')).toHaveLength(1)

    response.resolve(uploadedRecord)
    await waitFor(() => expect(screen.getAllByText('Ata.pdf')).toHaveLength(2))
    expect(input.value).toBe('')
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Enviar' }).disabled).toBe(true)
  })

  it('prevents duplicate submissions during upload', async () => {
    const response = pendingUpload()
    list.mockResolvedValue([])
    upload.mockReturnValue(response.promise)
    renderPage()
    await screen.findByText('Nenhum documento cadastrado.')
    const { input } = selectFile()

    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Enviando…' })
    expect(input.disabled).toBe(true)
    expect(button.disabled).toBe(true)
    expect(button.form).not.toBeNull()
    fireEvent.submit(button.form!)
    expect(upload).toHaveBeenCalledOnce()

    response.resolve(uploadedRecord)
    await screen.findByText('Ata.pdf')
  })

  it.each([
    [new ApiError(413, null), 'O arquivo excede o limite de envio.'],
    [new ApiError(422, null), 'O arquivo foi rejeitado. Selecione um arquivo válido.'],
    [new Error('Network error'), 'Não foi possível enviar o documento. Tente novamente.'],
  ])('keeps the selected file after upload failure: %s', async (error, message) => {
    list.mockResolvedValue([])
    upload.mockRejectedValueOnce(error).mockResolvedValueOnce(uploadedRecord)
    renderPage()
    await screen.findByText('Nenhum documento cadastrado.')
    const { file } = selectFile()

    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect((await screen.findByRole('alert')).textContent).toBe(message)
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(upload).toHaveBeenNthCalledWith(2, file)
    await screen.findByText('Ata.pdf')
  })

  it('logs out when the upload returns 401', async () => {
    setAccessToken('expired-token')
    list.mockResolvedValue([])
    upload.mockRejectedValue(new ApiError(401, null))
    renderPage()
    await screen.findByText('Nenhum documento cadastrado.')
    selectFile()

    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    await waitFor(() => expect(getAccessToken()).toBeNull())
  })

  it('shows loading before listing documents', async () => {
    list.mockResolvedValue([
      { id: 'first', original_filename: 'Certidão.pdf' },
      { id: 'second', original_filename: 'Certidão.pdf' },
    ])
    renderPage()

    expect(screen.getByRole('status').textContent).toContain('Carregando')
    expect(await screen.findAllByRole('listitem')).toHaveLength(2)
    expect(screen.getAllByText('Certidão.pdf')).toHaveLength(2)
  })

  it('shows the empty state', async () => {
    list.mockResolvedValue([])
    renderPage()

    expect(await screen.findByText('Nenhum documento cadastrado.')).toBeTruthy()
  })

  it('retries after a failed request', async () => {
    list.mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce([{ id: 'first', original_filename: 'Ata.pdf' }])
    renderPage()

    expect(await screen.findByRole('alert')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(await screen.findByText('Ata.pdf')).toBeTruthy()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('aborts the request on unmount', () => {
    list.mockResolvedValue([])
    const { unmount } = renderPage()
    const signal = list.mock.calls[0][0]

    expect(signal?.aborted).toBe(false)
    unmount()
    expect(signal?.aborted).toBe(true)
  })
})
