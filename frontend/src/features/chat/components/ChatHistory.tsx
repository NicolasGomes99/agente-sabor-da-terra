interface ChatHistoryProps {
  conversations: string[]
}

export function ChatHistory({ conversations }: ChatHistoryProps) {
  return (
    <aside className="chat-history" aria-label="Conversas recentes">
      <h2>Conversas</h2>
      <ul>
        {conversations.map((conversation, index) => (
          <li key={conversation}>
            <span
              className={index === 0 ? 'chat-history-item active' : 'chat-history-item'}
              aria-current={index === 0 ? 'page' : undefined}
            >
              {conversation}
            </span>
          </li>
        ))}
      </ul>
    </aside>
  )
}
