
import type { ChatMessage } from '../types'

interface MessageListProps {
  messages: ChatMessage[]
  className?: string
  ariaLabel?: string
  getPresentation?: (
    message: ChatMessage,
    index: number,
  ) => { className: string; author: string; authorClassName?: string }
}

export function MessageList({
  messages,
  className = 'message-list',
  ariaLabel = 'Histórico da conversa',
  getPresentation,
}: MessageListProps) {
  return (
    <div
      className={className}
      role="log"
      aria-label={ariaLabel}
      aria-live="polite"
    >
      {messages.map((message, index) => {
        const isAssistant = message.role === 'assistant'
        const presentation = getPresentation?.(message, index) ?? {
          className: `chat-message ${isAssistant ? 'assistant' : 'user'}`,
          author: isAssistant ? 'Assistente' : 'Você',
        }

        return (
          <article
            className={presentation.className}
            key={message.id}
          >
            <span className={presentation.authorClassName ?? 'message-author'}>
              {presentation.author}
            </span>

            <p>{message.content}</p>
          </article>
        )
      })}
    </div>
  )
}
