import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../../src/features/auth/AuthContext'
import {
  deleteDocument,
  getDocumentContent,
  listDocuments,
} from '../../../src/features/documents/documentsApi'
import { DocumentsPage } from '../../../src/features/documents/pages/DocumentsPage'
import { ApiError } from '../../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../../src/lib/auth-storage'

vi.mock('../../../src/features/documents/documentsApi', () => ({
  deleteDocument: vi.fn(),
  getDocumentContent: vi.fn(),
  listDocuments: vi.fn(),
}))

const remove = vi.mocked(deleteDocument)
const content = vi.mocked(getDocumentContent)
const list = vi.mocked(listDocuments)
const record = { id: 'first', original_filename: 'Certidão.pdf' }

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><DocumentsPage /></AuthProvider>
    </MemoryRouter>,
  )
}

function confirmDeletion(row: HTMLElement) {
  const actions = within(row)
  fireEvent.click(actions.getByRole('button', { name: 'Excluir' }))
  fireEvent.click(actions.getByRole('button', { name: 'Confirmar exclusão' }))
}

describe('DocumentsPage deletion', () => {
  beforeEach(() => {
    localStorage.clear()
    remove.mockReset()
    content.mockReset()
    list.mockReset()
    list.mockResolvedValue([record])
  })

  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('cancels deletion without calling the API', async () => {
    renderPage()
    const row = within(await screen.findByRole('listitem'))
    fireEvent.click(row.getByRole('button', { name: 'Excluir' }))

    expect(row.getByText('Excluir “Certidão.pdf”?')).toBeTruthy()
    expect(remove).not.toHaveBeenCalled()
    fireEvent.click(row.getByRole('button', { name: 'Cancelar' }))

    expect(row.queryByRole('button', { name: 'Confirmar exclusão' })).toBeNull()
    expect(row.getByText(record.original_filename)).toBeTruthy()
    expect(remove).not.toHaveBeenCalled()
  })

  it('deletes only the confirmed document after success', async () => {
    list.mockResolvedValue([record, { ...record, id: 'second' }])
    let finish!: () => void
    remove.mockReturnValueOnce(new Promise<void>((resolve) => { finish = resolve }))
    renderPage()
    const [first, second] = await screen.findAllByRole('listitem')

    confirmDeletion(second)

    expect(remove).toHaveBeenCalledExactlyOnceWith('second')
    expect(screen.getAllByRole('listitem')).toEqual([first, second])
    const pending = within(second).getByRole<HTMLButtonElement>('button', { name: 'Excluindo…' })
    expect(pending.disabled).toBe(true)
    fireEvent.click(pending)
    expect(remove).toHaveBeenCalledOnce()

    finish()
    await waitFor(() => expect(screen.getAllByRole('listitem')).toEqual([first]))
    expect(second.isConnected).toBe(false)
  })

  it('closes the preview when its document is deleted', async () => {
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', Object.assign(class extends URL {}, {
      createObjectURL: vi.fn(() => 'blob:preview'),
      revokeObjectURL,
    }))
    content.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    remove.mockResolvedValue(undefined)
    renderPage()
    const row = await screen.findByRole('listitem')
    fireEvent.click(within(row).getByRole('button', { name: 'Abrir' }))
    const viewer = await screen.findByTitle(record.original_filename)

    confirmDeletion(row)

    expect(await screen.findByText('Nenhum documento cadastrado.')).toBeTruthy()
    expect(viewer.isConnected).toBe(false)
    expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:preview')
  })

  it.each([
    [new ApiError(404, null), 'O documento não está mais disponível no servidor.'],
    [new Error('Network error'), 'Não foi possível confirmar a exclusão do documento.'],
  ])('keeps the document on failure and refreshes the list: %s', async (error, message) => {
    list.mockResolvedValueOnce([record]).mockResolvedValueOnce([])
    remove.mockRejectedValueOnce(error)
    renderPage()
    const row = await screen.findByRole('listitem')
    confirmDeletion(row)

    expect((await within(row).findByRole('alert')).textContent).toBe(message)
    expect(row.isConnected).toBe(true)
    fireEvent.click(within(row).getByRole('button', { name: 'Atualizar lista' }))

    expect(await screen.findByText('Nenhum documento cadastrado.')).toBeTruthy()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('logs out when deletion returns 401', async () => {
    setAccessToken('expired-token')
    remove.mockRejectedValueOnce(new ApiError(401, null))
    renderPage()
    confirmDeletion(await screen.findByRole('listitem'))

    await waitFor(() => expect(getAccessToken()).toBeNull())
  })
})
