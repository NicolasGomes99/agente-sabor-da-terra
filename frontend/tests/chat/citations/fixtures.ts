import type { ChatMessage, Citation } from '../../../src/features/chat/types'

export function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    message_id: 'message-1',
    chunk_id: 'chunk-1',
    document_id: 'document-1',
    document_name: 'politica-comercial-2026.txt',
    chunk_content: 'Cláusula 4.2: prazo de 48 horas úteis.',
    record_id: null,
    record_fields: null,
    source_type: 'excerpt',
    label: 'politica-comercial-2026.txt',
    view_url: '/documents/document-1/content',
    download_url: '/documents/document-1/download',
    ...overrides,
  }
}

export function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'message-1',
    role: 'assistant',
    content: 'Resposta do assistente.',
    position: 1,
    created_at: '2026-11-17T12:00:00Z',
    citations: [],
    ...overrides,
  }
}

export const excerptCitation = citation()

export const recordCitation = citation({
  chunk_id: 'chunk-lote-0094',
  document_id: 'document-lotes',
  document_name: 'lotes.csv',
  chunk_content:
    'lote_id=LOT-2026-0094; produtor_id=P004; produto=alface; quantidade=300; unidade=unidades',
  record_id: 'LOT-2026-0094',
  record_fields: {
    lote_id: 'LOT-2026-0094',
    produtor_id: 'P004',
    produto: 'alface',
    quantidade: '300',
    unidade: 'unidades',
    data_colheita: '2026-09-06',
    data_entrega_prevista: '2026-09-08',
  },
  source_type: 'record',
  label: 'lotes.csv - LOT-2026-0094',
})
