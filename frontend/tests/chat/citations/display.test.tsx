import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MessageList } from '../../../src/features/chat/components/MessageList'
import {
  citation, excerptCitation, message, recordCitation,
} from './fixtures'

describe('Chat citations display', () => {
  it('does not render a sources section without citations', () => {
    render(<MessageList messages={[message()]} />)

    expect(screen.queryByText('Fontes')).toBeNull()
    expect(screen.queryByRole('region', { name: 'Fontes da resposta' })).toBeNull()
  })

  it('renders a documentary excerpt as a source', () => {
    render(<MessageList messages={[message({ citations: [excerptCitation] })]} />)

    expect(screen.getByRole('region', { name: 'Fontes da resposta' })).toBeTruthy()
    expect(screen.getByText(excerptCitation.label)).toBeTruthy()
    expect(screen.getByText('Trecho')).toBeTruthy()
    expect(screen.getByText(excerptCitation.chunk_content)).toBeTruthy()
    expect(screen.queryByText(/Registro:/)).toBeNull()
  })

  it('renders a CSV record with its identifier and fields', () => {
    render(<MessageList messages={[message({ citations: [recordCitation] })]} />)

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
    render(<MessageList messages={[message({ citations: [recordWithoutFields] })]} />)

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
    render(
      <MessageList
        messages={[message({ citations: [excerptCitation, recordCitation, secondCitation] })]}
      />,
    )

    const region = screen.getByRole('region', { name: 'Fontes da resposta' })
    const items = within(region).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0].textContent).toContain(excerptCitation.label)
    expect(items[1].textContent).toContain(recordCitation.label)
    expect(items[2].textContent).toContain(secondCitation.label)
  })

  it('does not show sources on user messages', () => {
    render(
      <MessageList
        messages={[message({ role: 'user', citations: [recordCitation] })]}
      />,
    )

    expect(screen.queryByText('Fontes')).toBeNull()
    expect(screen.queryByText(recordCitation.label)).toBeNull()
  })
})
