import { AppShell } from '../../../components/layout/AppShell'
import { TriageBackLink } from './TriageBackLink'

type TriageChatStateVariant = 'loading' | 'not_found' | 'error'

interface TriageChatStateProps {
  variant: TriageChatStateVariant
  onRetry?: () => void
}

export function TriageChatState({
  variant,
  onRetry,
}: TriageChatStateProps) {
  return (
    <AppShell>
      <section className="triage-page" aria-labelledby="triage-chat-heading">
        <TriageBackLink />
        <h1 id="triage-chat-heading">
          {variant === 'not_found'
            ? 'Solicitação não encontrada'
            : 'Solicitação'}
        </h1>

        {variant === 'loading' && (
          <p role="status">Carregando solicitação…</p>
        )}
        {variant === 'not_found' && (
          <p>Esta solicitação não está mais disponível na fila.</p>
        )}
        {variant === 'error' && (
          <div className="triage-notice error">
            <p role="alert">Não foi possível carregar a solicitação.</p>
            <button
              className="triage-button"
              type="button"
              onClick={onRetry}
            >
              Tentar novamente
            </button>
          </div>
        )}
      </section>
    </AppShell>
  )
}
