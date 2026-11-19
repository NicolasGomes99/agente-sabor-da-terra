
import type { ChatMessage } from '../types'

import { CitationList } from './CitationList'

interface MessageListProps {
  messages: ChatMessage[]
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div
      className="message-list"
      role="log"
      aria-label="Histórico da conversa"
      aria-live="polite"
    >
      {messages.map((message) => {
        const isAssistant = message.role === 'assistant'

        return (
          <article
            className={`chat-message ${isAssistant ? 'assistant' : 'user'}`}
            key={message.id}
          >
            <span className="message-author">
              {isAssistant ? 'Assistente' : 'Você'}
            </span>

            <p>{message.content}</p>

            {isAssistant && <CitationList citations={message.citations} />}
          </article>
        )
      })}
    </div>
  )
}
