import type {
  SolicitationStatus,
  SolicitationType,
  SolicitationUrgency,
} from '../types'
import { TriageBadges } from './TriageBadges'

interface TriageChatHeaderProps {
  summary: string
  status: SolicitationStatus
  urgency: SolicitationUrgency
  requestType: SolicitationType
  readOnly: boolean
  confirmingFinalize: boolean
  onStartFinalize: () => void
}

export function TriageChatHeader({
  summary,
  status,
  urgency,
  requestType,
  readOnly,
  confirmingFinalize,
  onStartFinalize,
}: TriageChatHeaderProps) {
  return (
    <header className="triage-detail-heading">
      <div>
        <p className="triage-eyebrow">Conversa da solicitação</p>
        <h1 id="triage-chat-heading">{summary}</h1>
        <TriageBadges
          status={status}
          urgency={urgency}
          requestType={requestType}
        />
      </div>

      {!readOnly && !confirmingFinalize && (
        <button
          className="triage-button danger"
          type="button"
          onClick={onStartFinalize}
        >
          Encerrar solicitação
        </button>
      )}
    </header>
  )
}
