interface TriageQueueHeaderProps {
  countLabel: string
  onRefresh: () => void
}

export function TriageQueueHeader({
  countLabel,
  onRefresh,
}: TriageQueueHeaderProps) {
  return (
    <header className="triage-heading">
      <div>
        <p className="triage-eyebrow">Fila de trabalho</p>
        <h1 id="triage-heading">Triagem</h1>
        <p className="triage-count" aria-live="polite">
          {countLabel}
        </p>
      </div>
      <button className="triage-button" type="button" onClick={onRefresh}>
        Atualizar fila
      </button>
    </header>
  )
}
