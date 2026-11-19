
import { useState, type FormEvent, type KeyboardEvent } from 'react'

interface ChatInputProps {
  onSend: (content: string) => Promise<void>
  disabled?: boolean
}

export function ChatInput({
  onSend,
  disabled = false,
}: ChatInputProps) {
  const [content, setContent] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const message = content.trim()

    if (!message || disabled) return

    try {
      await onSend(message)
      setContent('')
    } catch {
      // A página apresenta a mensagem de erro.
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return

    event.preventDefault()
    if (!content.trim() || disabled) return
    event.currentTarget.form?.requestSubmit()
  }

  return (
    <form className="chat-input-area" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="chat-message">
        Mensagem para o assistente
      </label>

      <textarea
        id="chat-message"
        name="message"
        rows={1}
        placeholder="Digite sua mensagem..."
        value={content}
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
      />

      <button
        type="submit"
        disabled={disabled || !content.trim()}
        aria-label="Enviar mensagem"
      >
        ↑
      </button>
    </form>
  )
}
