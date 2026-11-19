import {
  solicitationStatusLabels,
  solicitationTypeLabels,
  solicitationUrgencyLabels,
  type SolicitationStatus,
  type SolicitationType,
  type SolicitationUrgency,
} from '../types'

interface TriageBadgesProps {
  status: SolicitationStatus
  urgency: SolicitationUrgency
  requestType?: SolicitationType
}

export function TriageBadges({
  status,
  urgency,
  requestType,
}: TriageBadgesProps) {
  return (
    <div className="triage-card-badges">
      <span className="triage-badge" data-status={status}>
        {solicitationStatusLabels[status]}
      </span>
      <span className="triage-badge" data-urgency={urgency}>
        {solicitationUrgencyLabels[urgency]}
      </span>
      {requestType ? (
        <span className="triage-badge" data-type={requestType}>
          {solicitationTypeLabels[requestType]}
        </span>
      ) : null}
    </div>
  )
}
