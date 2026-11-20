import { useEffect, useRef, useState } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import {
  PROCESSING_DELAY_WARNING_MS,
  createOperationId,
  extractExecutionFailure,
} from '../../chat/conversationOperation'
import {
  finalizeSolicitation,
  openSolicitationSession,
  sendSolicitationMessage,
} from '../triageApi'
import type { SolicitationSession } from '../types'
import { sortMessages, uniqueMessages } from '../utils'

type TriageChatDetailState =
  | { status: 'loading' }
  | { status: 'not_found' }
  | { status: 'error' }
  | { status: 'ready'; data: SolicitationSession }

type PendingTriageOperation = {
  operationId: string
  content: string
  persistedOnServer: boolean
}

export function useTriageChat(solicitationId: string | undefined) {
  const { logout } = useAuth()
  const [detail, setDetail] = useState<TriageChatDetailState>({
    status: 'loading',
  })
  const [attempt, setAttempt] = useState(0)
  const [sending, setSending] = useState(false)
  const [delayed, setDelayed] = useState(false)
  const [finalizing, setFinalizing] = useState(false)
  const [confirmingFinalize, setConfirmingFinalize] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [finalizeError, setFinalizeError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pendingOperation, setPendingOperation] =
    useState<PendingTriageOperation | null>(null)
  const [clearInputCount, setClearInputCount] = useState(0)

  const pageLifetime = useRef<AbortController | null>(null)
  const sendToken = useRef(0)
  const sendController = useRef<AbortController | null>(null)
  const delayTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingOperationRef = useRef<PendingTriageOperation | null>(null)
  const sendingRef = useRef(false)

  function clearDelayTimer() {
    if (delayTimer.current !== null) {
      clearTimeout(delayTimer.current)
      delayTimer.current = null
    }
  }

  useEffect(() => {
    const lifetime = new AbortController()
    pageLifetime.current = lifetime
    return () => {
      lifetime.abort()
      sendController.current?.abort()
      clearDelayTimer()
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    async function loadSession() {
      if (!solicitationId) {
        setDetail({ status: 'not_found' })
        return
      }

      setDetail({ status: 'loading' })
      try {
        const session = await openSolicitationSession(
          solicitationId,
          controller.signal,
        )
        if (!controller.signal.aborted) {
          setDetail({
            status: 'ready',
            data: {
              ...session,
              messages: sortMessages(session.messages),
            },
          })
        }
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }
        if (error instanceof ApiError && error.status === 404) {
          setDetail({ status: 'not_found' })
          return
        }
        setDetail({ status: 'error' })
      }
    }

    void loadSession()
    return () => controller.abort()
  }, [attempt, logout, solicitationId])

  async function executeSend(
    targetId: string,
    content: string,
    operationId: string,
    retryFlag: boolean,
  ): Promise<void> {
    const lifetime = pageLifetime.current
    if (!lifetime || lifetime.signal.aborted) return

    if (retryFlag) {
      sendController.current?.abort()
    } else if (sendingRef.current) {
      return
    }

    const token = ++sendToken.current
    const controller = new AbortController()
    sendController.current = controller
    sendingRef.current = true

    const existing = pendingOperationRef.current
    const currentOperation: PendingTriageOperation = {
      operationId,
      content,
      persistedOnServer: existing?.operationId === operationId
        ? existing.persistedOnServer
        : false,
    }
    pendingOperationRef.current = currentOperation
    setPendingOperation(currentOperation)

    clearDelayTimer()
    delayTimer.current = setTimeout(() => {
      if (!lifetime.signal.aborted && sendToken.current === token) {
        setDelayed(true)
      }
    }, PROCESSING_DELAY_WARNING_MS)

    setSending(true)
    setDelayed(false)
    setSendError(null)
    setNotice(null)

    const isCurrentAttempt = () =>
      !lifetime.signal.aborted && sendToken.current === token

    try {
      const payload = retryFlag
        ? { content, operation_id: operationId, retry: true }
        : { content, operation_id: operationId }
      const turn = await sendSolicitationMessage(
        targetId,
        payload,
        controller.signal,
      )
      if (!isCurrentAttempt()) return

      pendingOperationRef.current = null
      setPendingOperation(null)
      setClearInputCount((count) => count + 1)

      setDetail((current) => {
        if (current.status !== 'ready' || current.data.id !== targetId) {
          return current
        }
        return {
          status: 'ready',
          data: {
            ...current.data,
            summary: turn.solicitation.summary,
            request_type: turn.solicitation.request_type,
            urgency: turn.solicitation.urgency,
            status: turn.solicitation.status,
            read_only: turn.solicitation.status === 'finalizada',
            messages: sortMessages(uniqueMessages([
              ...current.data.messages,
              turn.user_message,
              turn.assistant_message,
            ])),
          },
        }
      })
    } catch (error) {
      if (!isCurrentAttempt()) return

      if (error instanceof ApiError && error.status === 401) {
        logout()
        throw error
      }

      if (error instanceof ApiError && error.status === 409) {
        const failure = extractExecutionFailure(error)
        const isFinalized =
          !failure.detail || failure.detail.toLowerCase().includes('finalizada')
        if (isFinalized) {
          pendingOperationRef.current = null
          setPendingOperation(null)
          setSendError('A conversa foi finalizada e não aceita novas mensagens.')
          setDetail((current) => current.status === 'ready'
            ? {
                status: 'ready',
                data: {
                  ...current.data,
                  status: 'finalizada',
                  read_only: true,
                },
              }
            : current)
        } else {
          setSendError(failure.detail ?? 'Não foi possível enviar a mensagem.')
        }
        throw error
      }

      const failure = extractExecutionFailure(error)
      const persistedUserMsg = failure.userMessage
      const resolvedOperationId = failure.operationId ?? operationId
      const updatedPending: PendingTriageOperation = {
        operationId: resolvedOperationId,
        content,
        persistedOnServer: Boolean(persistedUserMsg) || currentOperation.persistedOnServer,
      }
      pendingOperationRef.current = updatedPending
      setPendingOperation(updatedPending)

      if (persistedUserMsg) {
        setClearInputCount((count) => count + 1)
        setDetail((current) => {
          if (current.status !== 'ready' || current.data.id !== targetId) {
            return current
          }
          return {
            status: 'ready',
            data: {
              ...current.data,
              messages: sortMessages(uniqueMessages([
                ...current.data.messages,
                persistedUserMsg,
              ])),
            },
          }
        })
        setSendError(
          failure.detail ??
            'Não foi possível obter resposta do assistente. Tente novamente.',
        )
        return
      }

      setSendError(failure.detail ?? 'Não foi possível enviar a mensagem.')
      throw error
    } finally {
      if (sendToken.current === token) {
        clearDelayTimer()
        sendController.current = null
        sendingRef.current = false
        if (!lifetime.signal.aborted) {
          setSending(false)
          setDelayed(false)
        }
      }
    }
  }

  async function handleSendMessage(content: string): Promise<void> {
    if (!solicitationId || detail.status !== 'ready' || detail.data.read_only) {
      return
    }
    const existing = pendingOperationRef.current
    const reuseFailedDraft =
      existing !== null &&
      !existing.persistedOnServer &&
      existing.content === content
    const operationId = reuseFailedDraft ? existing.operationId : createOperationId()
    await executeSend(solicitationId, content, operationId, reuseFailedDraft)
  }

  function handleRetrySend() {
    if (!solicitationId || detail.status !== 'ready' || detail.data.read_only) {
      return
    }
    const pending = pendingOperationRef.current
    if (!pending) return
    void executeSend(
      solicitationId,
      pending.content,
      pending.operationId,
      true,
    ).catch(() => {
      // Estado de erro já exibido pelo ConversationStatusBanner.
    })
  }

  async function handleFinalize(): Promise<void> {
    if (!solicitationId || detail.status !== 'ready' || detail.data.read_only) {
      return
    }

    const targetId = solicitationId
    setFinalizing(true)
    setFinalizeError(null)
    setNotice(null)

    try {
      const solicitation = await finalizeSolicitation(targetId)
      const lifetime = pageLifetime.current
      if (lifetime?.signal.aborted) return

      // Aborta qualquer tentativa pendente no cliente ao finalizar a solicitação.
      sendToken.current += 1
      sendController.current?.abort()
      clearDelayTimer()
      sendingRef.current = false
      pendingOperationRef.current = null
      setSending(false)
      setDelayed(false)
      setPendingOperation(null)

      setDetail((current) => {
        if (current.status !== 'ready' || current.data.id !== targetId) {
          return current
        }
        return {
          status: 'ready',
          data: {
            ...current.data,
            ...solicitation,
            read_only: true,
          },
        }
      })
      setConfirmingFinalize(false)
      setNotice(
        'Solicitação finalizada. A conversa permanece disponível para consulta.',
      )
    } catch (error) {
      const lifetime = pageLifetime.current
      if (lifetime?.signal.aborted) return

      if (error instanceof ApiError && error.status === 401) {
        logout()
      } else if (error instanceof ApiError && error.status === 404) {
        setDetail({ status: 'not_found' })
      } else {
        setFinalizeError('Não foi possível finalizar a solicitação.')
      }
    } finally {
      const lifetime = pageLifetime.current
      if (!lifetime?.signal.aborted) setFinalizing(false)
    }
  }

  function startFinalize() {
    setConfirmingFinalize(true)
    setFinalizeError(null)
    setNotice(null)
  }

  function cancelFinalize() {
    setConfirmingFinalize(false)
    setFinalizeError(null)
  }

  function retry() {
    setAttempt((previous) => previous + 1)
  }

  return {
    detail,
    sending,
    delayed,
    finalizing,
    confirmingFinalize,
    sendError,
    finalizeError,
    notice,
    canRetrySend: pendingOperation !== null && detail.status === 'ready' && !detail.data.read_only,
    clearInputCount,
    handleSendMessage,
    handleRetrySend,
    handleFinalize,
    startFinalize,
    cancelFinalize,
    retry,
  }
}
