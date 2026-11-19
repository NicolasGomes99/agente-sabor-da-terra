import type { ChatMessage } from '../../chat/types'

interface TriageMessageListProps {
  messages: ChatMessage[]
}

export function TriageMessageList({
  messages,
}: TriageMessageListProps) {
  return (
    <div
      className="triage-message-list"
      role="log"
      aria-label="Histórico da conversa de triagem"
      aria-live="polite"
    >
      {messages.map((message, index) => {
        const isAssistant = message.role === 'assistant'
        const isOriginal = !isAssistant && index === 0
        const author = isAssistant
          ? 'Assistente'
          : isOriginal
            ? 'Mensagem original'
            : 'Funcionário'

        return (
          <article
            className={
              'triage-message ' +
              (isAssistant
                ? 'assistant'
                : isOriginal
                  ? 'original'
                  : 'staff')
            }
            key={message.id}
          >
            <span className="triage-message-author">{author}</span>
            <p>{message.content}</p>
          </article>
        )
      })}
    </div>
  )
}
