import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../../src/features/auth/AuthContext'
import { downloadDocument, listDocuments } from '../../../src/features/documents/documentsApi'
import { DocumentsPage } from '../../../src/features/documents/pages/DocumentsPage'
import { ApiError } from '../../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../../src/lib/auth-storage'

vi.mock('../../../src/features/documents/documentsApi', () => ({
  listDocuments: vi.fn(),
  downloadDocument: vi.fn(),
}))

const list = vi.mocked(listDocuments)
const download = vi.mocked(downloadDocument)
const createObjectURL = vi.fn(() => 'blob:download')
const revokeObjectURL = vi.fn()
const filename = 'Certidão da cooperativa.pdf'
const record = { id: 'first', original_filename: filename }

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><DocumentsPage /></AuthProvider>
    </MemoryRouter>,
  )
}

function pendingDownload() {
  let resolve!: (blob: Blob) => void
  const promise = new Promise<Blob>((complete) => { resolve = complete })
  download.mockReturnValueOnce(promise)
  return resolve
}

describe('DocumentsPage download', () => {
  beforeEach(() => {
    localStorage.clear()
    list.mockReset()
    list.mockResolvedValue([record])
    download.mockReset()
    createObjectURL.mockClear()
    revokeObjectURL.mockClear()
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL }))
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('downloads the selected document with its original filename', async () => {
    list.mockResolvedValue([record, { ...record, id: 'second' }])
    const blob = new Blob(['second file'])
    download.mockResolvedValueOnce(blob)
    const clickedLinks: HTMLAnchorElement[] = []
    vi.mocked(HTMLAnchorElement.prototype.click).mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.isConnected).toBe(true)
      clickedLinks.push(this)
    })
    renderPage()

    const buttons = await screen.findAllByRole('button', { name: 'Baixar' })
    fireEvent.click(buttons[1])

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:download'))
    expect(download).toHaveBeenCalledExactlyOnceWith('second')
    expect(createObjectURL).toHaveBeenCalledExactlyOnceWith(blob)
    expect(clickedLinks).toHaveLength(1)
    expect(clickedLinks[0].download).toBe(filename)
    expect(clickedLinks[0].href).toBe('blob:download')
    expect(clickedLinks[0].isConnected).toBe(false)
  })

  it('keeps other downloads available while one is pending', async () => {
    list.mockResolvedValue([record, { ...record, id: 'second' }])
    const resolve = pendingDownload()
    renderPage()
    const [first, second] = await screen.findAllByRole<HTMLButtonElement>('button', { name: 'Baixar' })

    fireEvent.click(first)
    expect(first.textContent).toBe('Baixando…')
    expect(first.disabled).toBe(true)
    expect(second.disabled).toBe(false)
    fireEvent.click(first)
    expect(download).toHaveBeenCalledExactlyOnceWith('first')

    await act(async () => resolve(new Blob(['file'])))
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledOnce())
    expect(first.disabled).toBe(false)
  })

  it('offers download for files without a preview', async () => {
    list.mockResolvedValue([{ id: 'zip', original_filename: 'Arquivo.zip' }])
    renderPage()

    expect(await screen.findByRole('button', { name: 'Baixar' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Abrir' })).toBeNull()
  })

  it.each([
    [new ApiError(404, null), 'O documento está indisponível.'],
    [new Error('Network error'), 'Não foi possível baixar o documento. Tente novamente.'],
  ])('shows download errors and allows retry: %s', async (error, message) => {
    download.mockRejectedValueOnce(error).mockResolvedValueOnce(new Blob(['file']))
    renderPage()
    const row = within(await screen.findByRole('listitem'))
    fireEvent.click(row.getByRole('button', { name: 'Baixar' }))

    expect((await row.findByRole('alert')).textContent).toBe(message)
    fireEvent.click(row.getByRole('button', { name: 'Baixar' }))
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledOnce())

    expect(download.mock.calls).toEqual([['first'], ['first']])
    expect(row.queryByRole('alert')).toBeNull()
  })

  it('logs out when the download returns 401', async () => {
    setAccessToken('expired-token')
    download.mockRejectedValueOnce(new ApiError(401, null))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Baixar' }))

    await waitFor(() => expect(getAccessToken()).toBeNull())
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it('does not start a download after leaving the page', async () => {
    const resolve = pendingDownload()
    const { unmount } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Baixar' }))
    expect(download).toHaveBeenCalledExactlyOnceWith('first')
    unmount()

    await act(async () => resolve(new Blob(['file'])))

    expect(createObjectURL).not.toHaveBeenCalled()
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })
})
