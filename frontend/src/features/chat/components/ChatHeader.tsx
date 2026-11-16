interface ChatHeaderProps {
  title: string
  subtitle: string
}

export function ChatHeader({ title, subtitle }: ChatHeaderProps) {
  return (
    <header className="chat-header">
      <div>
        <p className="chat-eyebrow">Assistente da cooperativa</p>
        <h1>{title}</h1>
        <p className="chat-subtitle">{subtitle}</p>
      </div>
      <span className="chat-status">Demonstração</span>
    </header>
  )
}
