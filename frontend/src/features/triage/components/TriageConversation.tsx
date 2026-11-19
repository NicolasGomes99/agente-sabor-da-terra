import { MessageList } from '../../chat/components/MessageList'
import { ChatInput } from '../../chat/components/ChatInput'
import type { ChatMessage } from '../../chat/types'
import type { SolicitationSession } from '../types'

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
      <MessageList
        messages={session.messages}
        className="triage-message-list"
        ariaLabel="Histórico da conversa de triagem"
        getPresentation={triageMessagePresentation}
      />

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
