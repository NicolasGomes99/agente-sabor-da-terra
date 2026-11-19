import { useEffect, useRef, useState } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
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

export function useTriageChat(solicitationId: string | undefined) {
  const { logout } = useAuth()
  const [detail, setDetail] = useState<TriageChatDetailState>({
    status: 'loading',
  })
  const [attempt, setAttempt] = useState(0)
  const [sending, setSending] = useState(false)
  const [finalizing, setFinalizing] = useState(false)
  const [confirmingFinalize, setConfirmingFinalize] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [finalizeError, setFinalizeError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const pageLifetime = useRef<AbortController | null>(null)

  useEffect(() => {
    const lifetime = new AbortController()
    pageLifetime.current = lifetime
    return () => lifetime.abort()
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

  async function handleSendMessage(content: string): Promise<void> {
    if (!solicitationId || detail.status !== 'ready' || detail.data.read_only) {
      return
    }

    const targetId = solicitationId
    setSending(true)
    setSendError(null)
    setNotice(null)

    try {
      const message = await sendSolicitationMessage(targetId, { content })
      const lifetime = pageLifetime.current
      if (lifetime?.signal.aborted) return

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
              message,
            ])),
          },
        }
      })
    } catch (error) {
      const lifetime = pageLifetime.current
      if (lifetime?.signal.aborted) return

      if (error instanceof ApiError && error.status === 401) {
        logout()
      } else if (error instanceof ApiError && error.status === 409) {
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
        setSendError('Não foi possível enviar a mensagem.')
      }
      throw error
    } finally {
      const lifetime = pageLifetime.current
      if (!lifetime?.signal.aborted) setSending(false)
    }
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
    finalizing,
    confirmingFinalize,
    sendError,
    finalizeError,
    notice,
    handleSendMessage,
    handleFinalize,
    startFinalize,
    cancelFinalize,
    retry,
  }
}
