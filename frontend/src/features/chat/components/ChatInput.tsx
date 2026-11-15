export function ChatInput() {
  return (
    <form className="chat-input-area">
      <label className="sr-only" htmlFor="chat-message">
        Mensagem para o assistente
      </label>
      <textarea
        id="chat-message"
        name="message"
        rows={1}
        placeholder="O chat será habilitado em uma próxima etapa."
        disabled
      />
      <button type="submit" disabled aria-label="Enviar mensagem">
        ↑
      </button>
    </form>
  )
}
