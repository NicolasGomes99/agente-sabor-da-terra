import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { message, recordCitation } from '../citations/fixtures'
import {
  detailA, read, renderPage, setupChatPageTests,
} from './helpers'

describe('ChatPage citations', () => {
  setupChatPageTests()

  it('shows persisted citations when reopening a conversation', async () => {
    read.mockResolvedValueOnce({
      ...detailA,
      messages: [
        message({
          content: 'O lote LOT-2026-0094 tem entrega prevista para 08/09/2026.',
          citations: [recordCitation],
        }),
      ],
    })
    renderPage()

    expect(await screen.findByText(recordCitation.label)).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Fontes da resposta' })).toBeTruthy()
    const card = screen.getByText(recordCitation.label).closest('li')
    expect(card?.textContent).toContain('Registro: LOT-2026-0094')
    expect(screen.getByText('produtor_id')).toBeTruthy()
    expect(screen.getByText('P004')).toBeTruthy()
  })
})
