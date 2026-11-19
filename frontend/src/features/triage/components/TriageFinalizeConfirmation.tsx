interface TriageFinalizeConfirmationProps {
  finalizing: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function TriageFinalizeConfirmation({
  finalizing,
  onCancel,
  onConfirm,
}: TriageFinalizeConfirmationProps) {
  return (
    <div
      className="triage-finalize-confirmation"
      role="group"
      aria-label="Confirmar encerramento da solicitação"
    >
      <p>
        Encerrar esta solicitação sem atendimento? A conversa continuará
        disponível para consulta.
      </p>
      <div className="triage-finalize-actions">
        <button
          className="triage-button"
          type="button"
          disabled={finalizing}
          onClick={onCancel}
        >
          Cancelar
        </button>
        <button
          className="triage-button danger"
          type="button"
          disabled={finalizing}
          onClick={onConfirm}
        >
          {finalizing ? 'Finalizando…' : 'Confirmar encerramento'}
        </button>
      </div>
    </div>
  )
}
