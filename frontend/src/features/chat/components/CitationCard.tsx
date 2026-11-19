import type { Citation } from '../types'

export function CitationCard({ citation }: { citation: Citation }) {
  const isRecord = citation.source_type === 'record'

  return (
    <li className="citation-card">
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
    </li>
  )
}
