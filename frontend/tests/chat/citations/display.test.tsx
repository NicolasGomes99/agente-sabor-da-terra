import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '../../../src/features/auth/AuthContext'
import { MessageList } from '../../../src/features/chat/components/MessageList'
import type { ChatMessage } from '../../../src/features/chat/types'
import {
  citation, excerptCitation, message, recordCitation,
} from './fixtures'

function renderMessages(messages: ChatMessage[]) {
  return render(
    <AuthProvider><MessageList messages={messages} /></AuthProvider>,
  )
}

describe('Chat citations display', () => {
  it('does not render a sources section without citations', () => {
    renderMessages([message()])

    expect(screen.queryByText('Fontes')).toBeNull()
    expect(screen.queryByRole('region', { name: 'Fontes da resposta' })).toBeNull()
  })

  it('renders a documentary excerpt as a source', () => {
    renderMessages([message({ citations: [excerptCitation] })])

    expect(screen.getByRole('region', { name: 'Fontes da resposta' })).toBeTruthy()
    expect(screen.getByText(excerptCitation.label)).toBeTruthy()
    expect(screen.getByText('Trecho')).toBeTruthy()
    expect(screen.getByText(excerptCitation.chunk_content)).toBeTruthy()
    expect(screen.queryByText(/Registro:/)).toBeNull()
  })

  it('renders a CSV record with its identifier and fields', () => {
    renderMessages([message({ citations: [recordCitation] })])

    const card = screen.getByText(recordCitation.label).closest('li')
    expect(card).toBeTruthy()
    expect(card?.textContent).toContain('Registro')
    expect(card?.textContent).toContain('Registro: LOT-2026-0094')

    for (const [field, value] of Object.entries(recordCitation.record_fields ?? {})) {
      expect(within(card as HTMLElement).getByText(field)).toBeTruthy()
      expect(card?.textContent).toContain(value)
    }

    expect(card?.textContent).not.toContain(recordCitation.chunk_content)
  })

  it('falls back to chunk content when a record has no fields', () => {
    const recordWithoutFields = citation({
      ...recordCitation,
      chunk_content: 'conteúdo do registro sem campos',
      record_fields: null,
    })
    renderMessages([message({ citations: [recordWithoutFields] })])

    const card = screen.getByText(recordWithoutFields.label).closest('li')
    expect(card?.textContent).toContain('Registro: LOT-2026-0094')
    expect(card?.textContent).toContain(recordWithoutFields.chunk_content)
  })

  it('lists every source of a message in order', () => {
    const secondCitation = citation({
      chunk_id: 'chunk-2',
      document_name: 'financeiro.csv',
      label: 'financeiro.csv - FIN-2026-006',
      record_id: 'FIN-2026-006',
      record_fields: { id_transacao: 'FIN-2026-006', valor: '1020.00' },
      source_type: 'record',
    })
    renderMessages([
      message({ citations: [excerptCitation, recordCitation, secondCitation] }),
    ])

    const region = screen.getByRole('region', { name: 'Fontes da resposta' })
    const items = within(region).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0].textContent).toContain(excerptCitation.label)
    expect(items[1].textContent).toContain(recordCitation.label)
    expect(items[2].textContent).toContain(secondCitation.label)
  })

  it('links each finding to its exact saved excerpt', () => {
    const contract = citation({
      ...excerptCitation,
      chunk_id: '54195469-bbb2-4eec-b71d-0e0104137395',
      chunk_content: 'Cláusula de certificação',
    })
    const capacity = citation({
      ...contract,
      chunk_id: 'eb85bc6d-459e-49a7-880d-12cd59b477cf',
      chunk_content: 'Limite semanal',
    })
    renderMessages([message({
      content: `Certificação [[fonte:${contract.chunk_id}]]\nCapacidade [[fonte:${capacity.chunk_id}]]`,
      citations: [capacity, contract],
    })])

    const targets = screen.getAllByRole('link', { name: contract.label }).map(
      link => document.getElementById(link.getAttribute('href')?.slice(1) ?? ''),
    )
    expect(targets[0]?.textContent).toContain(contract.chunk_content)
    expect(targets[1]?.textContent).toContain(capacity.chunk_content)
  })

  it('does not show sources on user messages', () => {
    renderMessages([
      message({ role: 'user', citations: [recordCitation] }),
    ])

    expect(screen.queryByText('Fontes')).toBeNull()
    expect(screen.queryByText(recordCitation.label)).toBeNull()
  })
})
