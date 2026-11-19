import { apiRequest } from '../../lib/api-client'
import type { ChatMessage } from '../chat/types'

import type {
  Solicitation,
  SolicitationMessagePayload,
  SolicitationSession,
} from './types'

export function listSolicitations(
  signal?: AbortSignal,
): Promise<Solicitation[]> {
  return apiRequest<Solicitation[]>('/solicitations', { signal })
}

export function getSolicitation(
  solicitationId: string,
  signal?: AbortSignal,
): Promise<Solicitation> {
  return apiRequest<Solicitation>(
    `/solicitations/${encodeURIComponent(solicitationId)}`,
    { signal },
  )
}

export function openSolicitationSession(
  solicitationId: string,
  signal?: AbortSignal,
): Promise<SolicitationSession> {
  return apiRequest<SolicitationSession>(
    `/solicitations/${encodeURIComponent(solicitationId)}/open`,
    { method: 'POST', signal },
  )
}

export function sendSolicitationMessage(
  solicitationId: string,
  payload: SolicitationMessagePayload,
): Promise<ChatMessage> {
  return apiRequest<ChatMessage>(
    `/solicitations/${encodeURIComponent(solicitationId)}/messages`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export function finalizeSolicitation(
  solicitationId: string,
): Promise<Solicitation> {
  return apiRequest<Solicitation>(
    `/solicitations/${encodeURIComponent(solicitationId)}/finalize`,
    { method: 'POST' },
  )
}
