import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../../src/features/auth/AuthContext'
import { MessageList } from '../../../src/features/chat/components/MessageList'
import type { ChatMessage } from '../../../src/features/chat/types'
import {
  downloadDocument,
  getDocumentContent,
} from '../../../src/features/documents/documentsApi'
import { ApiError } from '../../../src/lib/api-client'
import { clearAccessToken, getAccessToken, setAccessToken } from '../../../src/lib/auth-storage'
import { excerptCitation, message, recordCitation } from './fixtures'

vi.mock('../../../src/features/documents/documentsApi', () => ({
  downloadDocument: vi.fn(),
  getDocumentContent: vi.fn(),
}))

const content = vi.mocked(getDocumentContent)
const download = vi.mocked(downloadDocument)
const createObjectURL = vi.fn(() => 'blob:citation')
const revokeObjectURL = vi.fn()

function renderMessages(messages: ChatMessage[]) {
  return render(
    <AuthProvider><MessageList messages={messages} /></AuthProvider>,
  )
}

describe('Chat citation actions', () => {
  beforeEach(() => {
    clearAccessToken()
    content.mockReset()
    download.mockReset()
    createObjectURL.mockClear()
    revokeObjectURL.mockClear()
    vi.stubGlobal('URL', Object.assign(class extends URL {}, {
      createObjectURL,
      revokeObjectURL,
    }))
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  afterEach(() => {
    clearAccessToken()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('opens a text citation in the document preview', async () => {
    content.mockResolvedValue(new Blob(['Cláusula 4.2: prazo de 48 horas úteis.'], {
      type: 'text/plain',
    }))
    renderMessages([message({ citations: [excerptCitation] })])

    fireEvent.click(screen.getByRole('button', { name: `Abrir ${excerptCitation.label}` }))

    expect(await screen.findByText('Cláusula 4.2: prazo de 48 horas úteis.', {
      selector: 'pre',
    })).toBeTruthy()
    expect(screen.getByRole('heading', { name: excerptCitation.document_name })).toBeTruthy()
    expect(content).toHaveBeenCalledExactlyOnceWith(
      excerptCitation.document_id,
      expect.any(AbortSignal),
    )
  })

  it('opens a CSV record with the text preview', async () => {
    content.mockResolvedValue(new Blob(['lote_id,produto\nLOT-2026-0094,alface'], {
      type: 'text/csv',
    }))
    renderMessages([message({ citations: [recordCitation] })])

    fireEvent.click(screen.getByRole('button', { name: `Abrir ${recordCitation.label}` }))

    const csvPreview = await screen.findByText(
      (_, element) => element?.tagName === 'PRE'
        && element.textContent === 'lote_id,produto\nLOT-2026-0094,alface',
    )
    expect(csvPreview).toBeTruthy()
    expect(content).toHaveBeenCalledExactlyOnceWith(
      recordCitation.document_id,
      expect.any(AbortSignal),
    )
  })

  it('closes the preview and restores the open action', async () => {
    content.mockResolvedValue(new Blob(['conteúdo'], { type: 'text/plain' }))
    renderMessages([message({ citations: [excerptCitation] })])

    fireEvent.click(screen.getByRole('button', { name: `Abrir ${excerptCitation.label}` }))
    expect(await screen.findByText('conteúdo', { selector: 'pre' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))

    expect(screen.queryByText('conteúdo', { selector: 'pre' })).toBeNull()
    expect(screen.getByRole('button', { name: `Abrir ${excerptCitation.label}` })).toBeTruthy()
  })

  it('downloads a cited document with its original filename', async () => {
    const blob = new Blob(['arquivo citado'])
    download.mockResolvedValue(blob)
    const clickedLinks: HTMLAnchorElement[] = []
    vi.mocked(HTMLAnchorElement.prototype.click).mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clickedLinks.push(this)
    })
    renderMessages([message({ citations: [excerptCitation] })])

    fireEvent.click(screen.getByRole('button', { name: `Baixar ${excerptCitation.label}` }))

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledOnce())
    expect(download).toHaveBeenCalledExactlyOnceWith(excerptCitation.document_id)
    expect(createObjectURL).toHaveBeenCalledExactlyOnceWith(blob)
    expect(clickedLinks).toHaveLength(1)
    expect(clickedLinks[0].download).toBe(excerptCitation.document_name)
    expect(clickedLinks[0].isConnected).toBe(false)
  })

  it('prevents duplicate clicks while download is pending', async () => {
    let resolve!: (blob: Blob) => void
    download.mockReturnValueOnce(new Promise<Blob>((complete) => { resolve = complete }))
    renderMessages([message({ citations: [excerptCitation] })])
    const button = screen.getByRole<HTMLButtonElement>(
      'button',
      { name: `Baixar ${excerptCitation.label}` },
    )

    fireEvent.click(button)
    expect(button.textContent).toBe('Baixando…')
    expect(button.disabled).toBe(true)
    fireEvent.click(button)
    expect(download).toHaveBeenCalledExactlyOnceWith(excerptCitation.document_id)

    await act(async () => resolve(new Blob(['arquivo citado'])))
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledOnce())
    expect(button.disabled).toBe(false)
  })

  it.each([
    [new ApiError(404, null), 'O documento está indisponível.'],
    [new Error('Network error'), 'Não foi possível baixar o documento. Tente novamente.'],
  ])('shows download errors: %s', async (error, messageText) => {
    download.mockRejectedValue(error)
    renderMessages([message({ citations: [excerptCitation] })])

    fireEvent.click(screen.getByRole('button', { name: `Baixar ${excerptCitation.label}` }))

    expect((await screen.findByRole('alert')).textContent).toBe(messageText)
  })

  it('logs out when opening a citation returns 401', async () => {
    setAccessToken('expired-token')
    content.mockRejectedValue(new ApiError(401, null))
    renderMessages([message({ citations: [excerptCitation] })])

    fireEvent.click(screen.getByRole('button', { name: `Abrir ${excerptCitation.label}` }))

    await waitFor(() => expect(getAccessToken()).toBeNull())
  })

  it('logs out when downloading a citation returns 401', async () => {
    setAccessToken('expired-token')
    download.mockRejectedValue(new ApiError(401, null))
    renderMessages([message({ citations: [excerptCitation] })])

    fireEvent.click(screen.getByRole('button', { name: `Baixar ${excerptCitation.label}` }))

    await waitFor(() => expect(getAccessToken()).toBeNull())
    expect(createObjectURL).not.toHaveBeenCalled()
  })
})
