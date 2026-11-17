
import type { ChatSession } from '../types'

interface ChatHistoryProps {
  conversations: ChatSession[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onCreate: () => void
}

export function ChatHistory({
  conversations,
  activeSessionId,
  onSelect,
  onCreate,
}: ChatHistoryProps) {
  return (
    <aside className="chat-history" aria-label="Conversas recentes">
      <h2>Conversas</h2>

      <button type="button" onClick={onCreate}>
        + Nova conversa
      </button>

      <ul>
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              className={
                conversation.id === activeSessionId
                  ? 'chat-history-item active'
                  : 'chat-history-item'
              }
              aria-current={
                conversation.id === activeSessionId ? 'page' : undefined
              }
              onClick={() => onSelect(conversation.id)}
            >
              {conversation.title}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
