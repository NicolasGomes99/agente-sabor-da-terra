import { ChatInput } from '../../chat/components/ChatInput'
import { ConversationStatusBanner } from '../../chat/components/ConversationStatusBanner'
import { MessageList } from '../../chat/components/MessageList'
import type { ChatMessage } from '../../chat/types'
import type { SolicitationSession } from '../types'

interface TriageConversationProps {
  session: SolicitationSession
  sending: boolean
  delayed: boolean
  sendError: string | null
  canRetrySend: boolean
  clearInputCount: number
  onSend: (content: string) => Promise<void>
  onRetrySend: () => void
}

export function TriageConversation({
  session,
  sending,
  delayed,
  sendError,
  canRetrySend,
  clearInputCount,
  onSend,
  onRetrySend,
}: TriageConversationProps) {
  return (
    <div className="triage-conversation-card">
      <MessageList
        messages={session.messages}
        className="triage-message-list"
        ariaLabel="Histórico da conversa de triagem"
        getPresentation={triageMessagePresentation}
      />

      <ConversationStatusBanner
        sending={sending}
        delayed={delayed}
        error={sendError}
        canRetry={canRetrySend}
        onRetry={onRetrySend}
      />

      {!session.read_only ? (
        <ChatInput
          key={`${session.id}-${clearInputCount}`}
          onSend={onSend}
          disabled={sending}
        />
      ) : null}
    </div>
  )
}

function triageMessagePresentation(message: ChatMessage, index: number) {
  const isAssistant = message.role === 'assistant'
  const isOriginal = !isAssistant && index === 0
  const author = isAssistant
    ? 'Assistente'
    : isOriginal
      ? 'Mensagem original'
      : 'Funcionário'

  return {
    className:
      'triage-message ' +
      (isAssistant ? 'assistant' : isOriginal ? 'original' : 'staff'),
    author,
    authorClassName: 'triage-message-author',
  }
}
