import { Link } from 'react-router-dom'

import {
  solicitationTypeLabels,
  type Solicitation,
} from '../types'
import { TriageBadges } from './TriageBadges'

interface TriageSolicitationCardProps {
  solicitation: Solicitation
}

export function TriageSolicitationCard({
  solicitation,
}: TriageSolicitationCardProps) {
  return (
    <li>
      <article
        className="triage-card"
        aria-labelledby={`triage-summary-${solicitation.id}`}
      >
        <TriageBadges
          status={solicitation.status}
          urgency={solicitation.urgency}
        />
        <p className="triage-card-type">
          {solicitationTypeLabels[solicitation.request_type]}
        </p>
        <h2 id={`triage-summary-${solicitation.id}`}>
          {solicitation.summary}
        </h2>
        <p className="triage-card-hint">
          Análise, pendências e mensagem original disponíveis na
          conversa vinculada.
        </p>
        <div className="triage-card-footer">
          <Link
            className="triage-card-link"
            to={`/triagem/${encodeURIComponent(solicitation.id)}`}
            aria-label={`Abrir conversa: ${solicitation.summary}`}
          >
            Abrir conversa <span aria-hidden="true">→</span>
          </Link>
        </div>
      </article>
    </li>
  )
}
