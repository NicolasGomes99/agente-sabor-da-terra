import { useState } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { DocumentPreview } from '../../documents/components/DocumentPreview'
import { isTextDocument, saveDownload } from '../../documents/documentFiles'
import { downloadDocument } from '../../documents/documentsApi'
import type { Citation } from '../types'

type DownloadState =
  | { status: 'idle' }
  | { status: 'pending' }
  | { status: 'error'; message: string }

export function CitationCard({ citation }: { citation: Citation }) {
  const { logout } = useAuth()
  const [previewOpen, setPreviewOpen] = useState(false)
  const [download, setDownload] = useState<DownloadState>({ status: 'idle' })
  const isRecord = citation.source_type === 'record'

  async function handleDownload() {
    if (download.status === 'pending') return

    setDownload({ status: 'pending' })
    try {
      const blob = await downloadDocument(citation.document_id)
      saveDownload(blob, citation.document_name)
      setDownload({ status: 'idle' })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout()
        return
      }
      const status = error instanceof ApiError ? error.status : undefined
      setDownload({
        status: 'error',
        message: status === 404
          ? 'O documento está indisponível.'
          : 'Não foi possível baixar o documento. Tente novamente.',
      })
    }
  }

  return (
    <li id={`fonte-${citation.message_id}-${citation.chunk_id}`} className="citation-card">
      <div className="citation-card-header">
        <span className="citation-label">{citation.label}</span>
        <span className="citation-badge">
          {isRecord ? 'Registro' : 'Trecho'}
        </span>
      </div>

      {isRecord ? (
        <div className="citation-record">
          {citation.record_id && (
            <p className="citation-record-id">
              <span>Registro:</span> {citation.record_id}
            </p>
          )}

          {citation.record_fields && Object.keys(citation.record_fields).length > 0 ? (
            <dl className="citation-fields">
              {Object.entries(citation.record_fields).map(([field, value]) => (
                <div key={field}>
                  <dt>{field}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="citation-excerpt">{citation.chunk_content}</p>
          )}
        </div>
      ) : (
        <p className="citation-excerpt">{citation.chunk_content}</p>
      )}

      <div className="citation-actions">
        {!previewOpen && (
          <button
            type="button"
            aria-label={`Abrir ${citation.label}`}
            onClick={() => setPreviewOpen(true)}
          >
            Abrir
          </button>
        )}
        <button
          type="button"
          aria-label={`Baixar ${citation.label}`}
          disabled={download.status === 'pending'}
          onClick={() => void handleDownload()}
        >
          {download.status === 'pending' ? 'Baixando…' : 'Baixar'}
        </button>
      </div>

      {download.status === 'error' && (
        <p className="citation-action-error" role="alert">{download.message}</p>
      )}

      {previewOpen && (
        <DocumentPreview
          key={citation.document_id}
          document={{
            id: citation.document_id,
            original_filename: citation.document_name,
          }}
          asText={isTextDocument(citation.document_name)}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </li>
  )
}
