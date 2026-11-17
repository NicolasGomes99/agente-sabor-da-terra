import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { listDocuments } from '../../src/features/documents/documentsApi'
import { DocumentsPage } from '../../src/features/documents/pages/DocumentsPage'

vi.mock('../../src/features/documents/documentsApi', () => ({ listDocuments: vi.fn() }))
const list = vi.mocked(listDocuments)

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><DocumentsPage /></AuthProvider>
    </MemoryRouter>,
  )
}

describe('DocumentsPage', () => {
  beforeEach(() => list.mockReset())

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
