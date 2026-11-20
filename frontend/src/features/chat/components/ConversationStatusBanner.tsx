interface ConversationStatusBannerProps {
  sending: boolean
  delayed: boolean
  recoveredProcessing?: boolean
  error: string | null
  canRetry: boolean
  onRetry?: () => void
}

export function ConversationStatusBanner({
  sending,
  delayed,
  recoveredProcessing = false,
  error,
  canRetry,
  onRetry,
}: ConversationStatusBannerProps) {
  if (sending) {
    return (
      <div
        className={`conversation-status ${delayed ? 'delayed' : 'processing'}`}
        role="status"
        aria-live="polite"
      >
        <p>
          {delayed
            ? 'O processamento está demorando mais que o esperado. Você pode continuar aguardando ou tentar novamente.'
            : 'Assistente processando resposta…'}
        </p>

        {delayed && canRetry && onRetry && (
          <button
            type="button"
            className="conversation-retry-button"
            onClick={onRetry}
          >
            Tentar novamente
          </button>
        )}
      </div>
    )
  }

  if (recoveredProcessing && canRetry && onRetry) {
    return (
      <div
        className="conversation-status delayed"
        role="status"
        aria-live="polite"
      >
        <p>
          A última mensagem ainda está em processamento ou foi interrompida. Você pode tentar novamente para concluir a resposta.
        </p>

        <button
          type="button"
          className="conversation-retry-button"
          onClick={onRetry}
        >
          Tentar novamente
        </button>
      </div>
    )
  }

  if (error) {
    return (
      <div className="conversation-status error" role="alert">
        <p>{error}</p>

        {canRetry && onRetry && (
          <button
            type="button"
            className="conversation-retry-button"
            onClick={onRetry}
          >
            Tentar novamente
          </button>
        )}
      </div>
    )
  }

  return null
}
