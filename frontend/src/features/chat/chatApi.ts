
import { apiRequest } from '../../lib/api-client'

import type {
  ChatMessage,
  ChatSession,
  ChatSessionDetail,
  CreateMessagePayload,
} from './types'

export function listChatSessions(): Promise<ChatSession[]> {
  return apiRequest<ChatSession[]>('/chat/sessions')
}

export function createChatSession(): Promise<ChatSession> {
  return apiRequest<ChatSession>('/chat/sessions', {
    method: 'POST',
  })
}

export function getChatSession(
  sessionId: string,
): Promise<ChatSessionDetail> {
  return apiRequest<ChatSessionDetail>(
    `/chat/sessions/${sessionId}`,
  )
}

export function sendChatMessage(
  sessionId: string,
  payload: CreateMessagePayload,
): Promise<ChatMessage> {
  return apiRequest<ChatMessage>(
    `/chat/sessions/${sessionId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}
