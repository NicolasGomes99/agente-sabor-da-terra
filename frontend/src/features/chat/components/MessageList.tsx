
import type { ChatMessage } from '../types'

import { CitationList } from './CitationList'

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

            <p>{isAssistant ? message.content.split(/(\[\[fonte:[0-9a-f-]{36}\]\])/gi).map((part, partIndex) => {
              const chunkId = /^\[\[fonte:([0-9a-f-]{36})\]\]$/i.exec(part)?.[1]
              if (!chunkId) return part
              const citation = message.citations?.find((source) => source.chunk_id === chunkId)
              if (!citation) return 'Fonte indisponível'
              return (
                <a key={partIndex} href={`#fonte-${citation.message_id}-${citation.chunk_id}`}>
                  {citation.label}
                </a>
              )
            }) : message.content}</p>

            {isAssistant && <CitationList citations={message.citations} />}
          </article>
        )
      })}
    </div>
  )
}
