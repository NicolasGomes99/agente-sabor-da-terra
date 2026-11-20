import { ApiError } from '../../lib/api-client'
import type { ChatMessage } from './types'

export const PROCESSING_DELAY_WARNING_MS = 60_000

let fallbackOperationCounter = 0

export function createOperationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  fallbackOperationCounter += 1
  return `op-${Date.now()}-${fallbackOperationCounter}`
}

export interface ExecutionFailureInfo {
  detail?: string
  operationId?: string
  userMessage?: ChatMessage
}

function isChatMessageLike(value: unknown): value is ChatMessage {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.role === 'string' &&
    typeof candidate.content === 'string' &&
    typeof candidate.position === 'number' &&
    typeof candidate.created_at === 'string' &&
    Array.isArray(candidate.citations)
  )
}

export function extractExecutionFailure(error: unknown): ExecutionFailureInfo {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== 'object') {
    return {}
  }
  const details = error.details as Record<string, unknown>
  return {
    detail: typeof details.detail === 'string' ? details.detail : undefined,
    operationId:
      typeof details.operation_id === 'string' ? details.operation_id : undefined,
    userMessage: isChatMessageLike(details.user_message)
      ? details.user_message
      : undefined,
  }
}
