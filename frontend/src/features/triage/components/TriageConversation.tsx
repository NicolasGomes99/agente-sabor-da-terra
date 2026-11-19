import { ChatInput } from '../../chat/components/ChatInput'
import type { SolicitationSession } from '../types'
import { TriageMessageList } from './TriageMessageList'

interface TriageConversationProps {
  session: SolicitationSession
  sending: boolean
  sendError: string | null
  onSend: (content: string) => Promise<void>
}

export function TriageConversation({
  session,
  sending,
  sendError,
  onSend,
}: TriageConversationProps) {
  return (
    <div className="triage-conversation-card">
      <TriageMessageList messages={session.messages} />

      {sendError && (
        <p className="triage-action-error" role="alert">{sendError}</p>
      )}

      {!session.read_only ? (
        <ChatInput
          key={session.id}
          onSend={onSend}
          disabled={sending}
        />
      ) : null}
    </div>
  )
}
