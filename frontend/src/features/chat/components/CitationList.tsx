import type { Citation } from '../types'

import { CitationCard } from './CitationCard'

export function CitationList({ citations }: { citations?: Citation[] }) {
  if (!citations?.length) return null

  return (
    <section className="citation-list" aria-label="Fontes da resposta">
      <p className="citation-list-title">Fontes</p>
      <ul>
        {citations.map((citation) => (
          <CitationCard key={citation.chunk_id} citation={citation} />
        ))}
      </ul>
    </section>
  )
}
