
import { apiRequest } from '../../lib/api-client'

import type {
  ChatSession,
  ChatSessionDetail,
  ChatTurnResponse,
  CreateMessagePayload,
} from './types'

export function listChatSessions(signal?: AbortSignal): Promise<ChatSession[]> {
  return apiRequest<ChatSession[]>('/chat/sessions', { signal })
}

export function createChatSession(): Promise<ChatSession> {
  return apiRequest<ChatSession>('/chat/sessions', {
    method: 'POST',
  })
}

export function getChatSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ChatSessionDetail> {
  return apiRequest<ChatSessionDetail>(
    `/chat/sessions/${sessionId}`,
    { signal },
  )
}

export function sendChatMessage(
  sessionId: string,
  payload: CreateMessagePayload,
  signal?: AbortSignal,
): Promise<ChatTurnResponse> {
  const options: RequestInit = {
    method: 'POST',
    body: JSON.stringify(payload),
  }
  if (signal !== undefined) {
    options.signal = signal
  }
  return apiRequest<ChatTurnResponse>(
    `/chat/sessions/${sessionId}/messages`,
    options,
  )
}
