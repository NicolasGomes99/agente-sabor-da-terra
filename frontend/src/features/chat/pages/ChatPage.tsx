
import { useCallback, useEffect, useState } from 'react'

import { AppShell } from '../../../components/layout/AppShell'
import { ChatHeader } from '../components/ChatHeader'
import { ChatHistory } from '../components/ChatHistory'
import { ChatInput } from '../components/ChatInput'
import { MessageList } from '../components/MessageList'

import {
  createChatSession,
  getChatSession,
  listChatSessions,
  sendChatMessage,
} from '../chatApi'

import type { ChatMessage, ChatSession } from '../types'

import './chat.css'

export function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId)
    setMessages([])
    setError(null)
    setLoading(true)

    try {
      const session = await getChatSession(sessionId)
      setMessages(session.messages)
    } catch {
      setError('Não foi possível carregar as mensagens.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    async function loadSessions() {
      try {
        const data = await listChatSessions()
        setSessions(data)

        if (data.length > 0) {
          await selectSession(data[0].id)
        }
      } catch {
        setError('Não foi possível carregar as conversas.')
      } finally {
        setLoading(false)
      }
    }

    void loadSessions()
  }, [selectSession])

  async function handleCreateSession() {
    setError(null)
    setLoading(true)

    try {
      const session = await createChatSession()

      setSessions((current) => [session, ...current])
      setActiveSessionId(session.id)
      setMessages([])
    } catch {
      setError('Não foi possível criar uma nova conversa.')
    } finally {
      setLoading(false)
    }
  }

  async function handleSendMessage(content: string) {
    if (!activeSessionId) return

    setSending(true)
    setError(null)

    try {
      const message = await sendChatMessage(activeSessionId, { content })

      setMessages((current) => [...current, message])
    } catch {
      setError('Não foi possível enviar a mensagem.')
      throw new Error('Message sending failed')
    } finally {
      setSending(false)
    }
  }

  return (
    <AppShell>
      <div className="chat-page">
        <ChatHistory
          conversations={sessions}
          activeSessionId={activeSessionId}
          onSelect={selectSession}
          onCreate={handleCreateSession}
        />

        <section className="chat-workspace" aria-label="Chat da cooperativa">
          <ChatHeader
            title={
              sessions.find((session) => session.id === activeSessionId)
                ?.title ?? 'Novo chat'
            }
            subtitle="Consulte informações da operação da cooperativa."
          />

          {error && <p role="alert">{error}</p>}

          {loading ? (
            <p>Carregando conversa...</p>
          ) : (
            <MessageList messages={messages} />
          )}

          <ChatInput
            onSend={handleSendMessage}
            disabled={!activeSessionId || loading || sending}
          />
        </section>
      </div>
    </AppShell>
  )
}
