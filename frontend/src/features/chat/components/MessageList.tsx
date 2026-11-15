interface ChatMessage {
  id: string
  author: 'assistant' | 'user'
  text: string
}

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
      {messages.map((message) => (
        <article className={`chat-message ${message.author}`} key={message.id}>
          <span className="message-author">
            {message.author === 'assistant' ? 'Assistente' : 'Você'}
          </span>
          <p>{message.text}</p>
        </article>
      ))}
    </div>
  )
}
