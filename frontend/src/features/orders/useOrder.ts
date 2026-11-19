import { useEffect, useState } from 'react'

import { ApiError } from '../../lib/api-client'
import { useAuth } from '../auth/useAuth'
import { orderError } from './orderHelpers'
import { getOrder, type OrderRecord } from './ordersApi'

type OrderState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; order: OrderRecord }

export function useOrder(id: string) {
  const { logout } = useAuth()

  const [state, setState] = useState<OrderState>({
    status: 'loading',
  })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    void getOrder(id, controller.signal)
      .then((order) => {
        if (!controller.signal.aborted) {
          setState({ status: 'ready', order })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return

        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }

        setState({
          status: 'error',
          message: orderError(error),
        })
      })

    return () => controller.abort()
  }, [id, attempt, logout])

  function retry() {
    setState({ status: 'loading' })
    setAttempt((value) => value + 1)
  }

  return { state, setState, retry }
}