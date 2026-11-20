import { useCallback, useEffect, useRef, useState } from 'react'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { OrderDraftPanel } from '../../orders/components/OrderDraftPanel'
import { ChatHeader } from '../components/ChatHeader'
import { ChatHistory } from '../components/ChatHistory'
import { ChatInput } from '../components/ChatInput'
import { ConversationStatusBanner } from '../components/ConversationStatusBanner'
import { MessageList } from '../components/MessageList'
import {
  PROCESSING_DELAY_WARNING_MS,
  createOperationId,
  extractExecutionFailure,
} from '../conversationOperation'
import {
  createChatSession,
  getChatSession,
  listChatSessions,
  sendChatMessage,
} from '../chatApi'
import type { ChatMessage, ChatSession } from '../types'

import './chat.css'

type PendingOperation = {
  operationId: string
  content: string
  persistedOnServer: boolean
}

type ConversationState = {
  messages: ChatMessage[]
  loading: boolean
  sending: boolean
  delayed: boolean
  loadError: string | null
  sendError: string | null
  pendingOperation: PendingOperation | null
  clearInputCount: number
}

const emptyConversation: ConversationState = {
  messages: [],
  loading: false,
  sending: false,
  delayed: false,
  loadError: null,
  sendError: null,
  pendingOperation: null,
  clearInputCount: 0,
}

function uniqueById<T extends { id: string }>(items: T[]): T[] {
  return [...new Map(items.map((item) => [item.id, item])).values()]
}

function sortMessages(messages: ChatMessage[]): ChatMessage[] {
  return [...messages].sort((left, right) =>
    left.position - right.position ||
    left.created_at.localeCompare(right.created_at) ||
    left.id.localeCompare(right.id)
  )
}

export function ChatPage() {
  const { logout } = useAuth()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<
    Record<string, ConversationState | undefined>
  >({})
  const [listing, setListing] = useState(true)
  const [creating, setCreating] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const pageLifetime = useRef<AbortController | null>(null)
  const messageRead = useRef<AbortController | null>(null)
  const selectionRevision = useRef(0)
  const createInProgress = useRef(false)
  const pendingSends = useRef(new Set<string>())
  const sendTokens = useRef(new Map<string, number>())
  const sendControllers = useRef(new Map<string, AbortController>())
  const delayTimers = useRef(new Map<string, ReturnType<typeof setTimeout>>())
  const pendingOperationsRef = useRef(new Map<string, PendingOperation>())
  const confirmedMessages = useRef(new Map<string, ChatMessage[]>())

  const updateConversation = useCallback((
    sessionId: string, patch: Partial<ConversationState>,
  ) => {
    setConversations((current) => ({
      ...current,
      [sessionId]: { ...(current[sessionId] ?? emptyConversation), ...patch },
    }))
  }, [])

  const clearDelayTimer = useCallback((sessionId: string) => {
    const timer = delayTimers.current.get(sessionId)
    if (timer !== undefined) {
      clearTimeout(timer)
      delayTimers.current.delete(sessionId)
    }
  }, [])

  const abortAllSends = useCallback(() => {
    for (const controller of sendControllers.current.values()) {
      controller.abort()
    }
    sendControllers.current.clear()
    for (const timer of delayTimers.current.values()) {
      clearTimeout(timer)
    }
    delayTimers.current.clear()
  }, [])

  const expireSession = useCallback((error: unknown, lifetime: AbortController) => {
    if (error instanceof ApiError && error.status === 401) {
      lifetime.abort()
      messageRead.current?.abort()
      abortAllSends()
      logout()
      return true
    }
    return false
  }, [abortAllSends, logout])

  const selectSession = useCallback(async (sessionId: string) => {
    const lifetime = pageLifetime.current
    if (!lifetime || lifetime.signal.aborted) return

    selectionRevision.current += 1
    messageRead.current?.abort()
    const controller = new AbortController()
    messageRead.current = controller
    setActiveSessionId(sessionId)
    setListError(null)
    setCreateError(null)
    updateConversation(sessionId, { loading: true, loadError: null })

    const isCurrentRead = () =>
      !lifetime.signal.aborted && !controller.signal.aborted &&
      messageRead.current === controller

    try {
      const session = await getChatSession(sessionId, controller.signal)
      if (!isCurrentRead()) return

      // A read may have started before an in-flight send was committed.
      updateConversation(sessionId, {
        messages: sortMessages(uniqueById([
          ...session.messages,
          ...(confirmedMessages.current.get(sessionId) ?? []),
        ])),
      })
    } catch (error) {
      if (!isCurrentRead() || expireSession(error, lifetime)) return
      updateConversation(sessionId, {
        loadError: 'Não foi possível carregar as mensagens.',
      })
    } finally {
      if (isCurrentRead()) {
        messageRead.current = null
        updateConversation(sessionId, { loading: false })
      }
    }
  }, [expireSession, updateConversation])

  useEffect(() => {
    const lifetime = new AbortController()
    pageLifetime.current = lifetime
    const initialRevision = selectionRevision.current

    async function loadSessions() {
      try {
        const data = await listChatSessions(lifetime.signal)
        if (lifetime.signal.aborted) return
        setSessions((current) => uniqueById([...current, ...data]))

        if (selectionRevision.current === initialRevision && data.length > 0) {
          void selectSession(data[0].id)
        }
      } catch (error) {
        if (lifetime.signal.aborted || expireSession(error, lifetime)) return
        if (selectionRevision.current === initialRevision) {
          setListError('Não foi possível carregar as conversas.')
        }
      } finally {
        if (!lifetime.signal.aborted) setListing(false)
      }
    }

    void loadSessions()
    return () => {
      lifetime.abort()
      messageRead.current?.abort()
      abortAllSends()
    }
  }, [abortAllSends, expireSession, selectSession])

  async function handleCreateSession() {
    const lifetime = pageLifetime.current
    if (!lifetime || lifetime.signal.aborted || createInProgress.current) return

    createInProgress.current = true
    const revision = ++selectionRevision.current
    setCreating(true)
    setListError(null)
    setCreateError(null)

    try {
      const session = await createChatSession()
      if (lifetime.signal.aborted) return
      setSessions((current) => uniqueById([session, ...current]))

      if (selectionRevision.current === revision) {
        messageRead.current?.abort()
        messageRead.current = null
        updateConversation(session.id, emptyConversation)
        setActiveSessionId(session.id)
      }
    } catch (error) {
      if (lifetime.signal.aborted || expireSession(error, lifetime)) return
      if (selectionRevision.current === revision) {
        setCreateError('Não foi possível criar uma nova conversa.')
      }
    } finally {
      createInProgress.current = false
      if (!lifetime.signal.aborted) setCreating(false)
    }
  }

  async function executeSend(
    sessionId: string,
    content: string,
    operationId: string,
    retry: boolean,
  ): Promise<void> {
    const lifetime = pageLifetime.current
    if (!lifetime || lifetime.signal.aborted) return

    if (retry) {
      sendControllers.current.get(sessionId)?.abort()
    } else if (pendingSends.current.has(sessionId)) {
      return
    }

    const token = (sendTokens.current.get(sessionId) ?? 0) + 1
    sendTokens.current.set(sessionId, token)
    const controller = new AbortController()
    sendControllers.current.set(sessionId, controller)
    pendingSends.current.add(sessionId)

    const existingPending = pendingOperationsRef.current.get(sessionId)
    const currentOperation: PendingOperation = {
      operationId,
      content,
      persistedOnServer: existingPending?.operationId === operationId
        ? existingPending.persistedOnServer
        : false,
    }
    pendingOperationsRef.current.set(sessionId, currentOperation)

    clearDelayTimer(sessionId)
    const timer = setTimeout(() => {
      if (
        !lifetime.signal.aborted &&
        sendTokens.current.get(sessionId) === token
      ) {
        updateConversation(sessionId, { delayed: true })
      }
    }, PROCESSING_DELAY_WARNING_MS)
    delayTimers.current.set(sessionId, timer)

    updateConversation(sessionId, {
      sending: true,
      delayed: false,
      sendError: null,
      pendingOperation: currentOperation,
    })

    const isCurrentAttempt = () =>
      !lifetime.signal.aborted && sendTokens.current.get(sessionId) === token

    try {
      const payload = retry
        ? { content, operation_id: operationId, retry: true }
        : { content, operation_id: operationId }
      const turn = await sendChatMessage(sessionId, payload, controller.signal)
      if (!isCurrentAttempt()) return

      const newMessages = [turn.user_message, turn.assistant_message]
      confirmedMessages.current.set(sessionId, uniqueById([
        ...(confirmedMessages.current.get(sessionId) ?? []),
        ...newMessages,
      ]))
      pendingOperationsRef.current.delete(sessionId)

      setConversations((current) => {
        const conversation = current[sessionId] ?? emptyConversation
        return {
          ...current,
          [sessionId]: {
            ...conversation,
            messages: sortMessages(uniqueById([
              ...conversation.messages,
              ...newMessages,
            ])),
            pendingOperation: null,
            sendError: null,
            delayed: false,
            clearInputCount: conversation.clearInputCount + 1,
          },
        }
      })
    } catch (error) {
      if (!isCurrentAttempt()) return
      if (expireSession(error, lifetime)) return

      const failure = extractExecutionFailure(error)
      const persistedUserMsg = failure.userMessage
      const resolvedOperationId = failure.operationId ?? operationId
      const updatedPending: PendingOperation = {
        operationId: resolvedOperationId,
        content,
        persistedOnServer: Boolean(persistedUserMsg) || currentOperation.persistedOnServer,
      }
      pendingOperationsRef.current.set(sessionId, updatedPending)

      if (persistedUserMsg) {
        confirmedMessages.current.set(sessionId, uniqueById([
          ...(confirmedMessages.current.get(sessionId) ?? []),
          persistedUserMsg,
        ]))
        setConversations((current) => {
          const conversation = current[sessionId] ?? emptyConversation
          return {
            ...current,
            [sessionId]: {
              ...conversation,
              messages: sortMessages(uniqueById([
                ...conversation.messages,
                persistedUserMsg,
              ])),
              sendError:
                failure.detail ??
                'Não foi possível obter resposta do assistente. Tente novamente.',
              pendingOperation: updatedPending,
              delayed: false,
              clearInputCount: conversation.clearInputCount + 1,
            },
          }
        })
        return
      }

      updateConversation(sessionId, {
        sendError: failure.detail ?? 'Não foi possível enviar a mensagem.',
        pendingOperation: updatedPending,
        delayed: false,
      })
      throw error
    } finally {
      if (sendTokens.current.get(sessionId) === token) {
        clearDelayTimer(sessionId)
        sendControllers.current.delete(sessionId)
        pendingSends.current.delete(sessionId)
        if (!lifetime.signal.aborted) {
          updateConversation(sessionId, { sending: false, delayed: false })
        }
      }
    }
  }

  async function handleSendMessage(content: string) {
    const sessionId = activeSessionId
    if (!sessionId) return
    const existing = pendingOperationsRef.current.get(sessionId)
    const reuseFailedDraft =
      existing !== undefined &&
      !existing.persistedOnServer &&
      existing.content === content
    const operationId = reuseFailedDraft ? existing.operationId : createOperationId()
    await executeSend(sessionId, content, operationId, reuseFailedDraft)
  }

  function handleRetryActiveSession() {
    const sessionId = activeSessionId
    if (!sessionId) return
    const pending = pendingOperationsRef.current.get(sessionId)
    if (!pending) return
    void executeSend(
      sessionId,
      pending.content,
      pending.operationId,
      true,
    ).catch(() => {
      // Estado de erro já apresentado pelo ConversationStatusBanner.
    })
  }

  const conversation = (activeSessionId && conversations[activeSessionId]) || emptyConversation
  const loading = conversation.loading || (!activeSessionId && (listing || creating))
  const errors = [listError, createError, conversation.loadError]

  return (
    <AppShell>
      <div className="chat-page">
        <ChatHistory
          conversations={sessions}
          activeSessionId={activeSessionId}
          creating={creating}
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

          {errors.map((error) => error && <p key={error} role="alert">{error}</p>)}

          {loading ? (
            <p>Carregando conversa...</p>
          ) : (
            <MessageList messages={conversation.messages} />
          )}

          <ConversationStatusBanner
            sending={conversation.sending}
            delayed={conversation.delayed}
            error={conversation.sendError}
            canRetry={conversation.pendingOperation !== null}
            onRetry={handleRetryActiveSession}
          />

          {activeSessionId && (
            <OrderDraftPanel scope={{ kind: 'chat', id: activeSessionId }} />
          )}

          <ChatInput
            key={`${activeSessionId ?? 'no-session'}-${conversation.clearInputCount}`}
            onSend={handleSendMessage}
            disabled={!activeSessionId || loading || conversation.sending}
          />
        </section>
      </div>
    </AppShell>
  )
}
