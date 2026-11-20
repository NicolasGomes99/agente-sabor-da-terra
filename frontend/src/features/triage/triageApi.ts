import { apiRequest } from '../../lib/api-client'

import type {
  Solicitation,
  SolicitationMessagePayload,
  SolicitationSession,
  SolicitationTurnResponse,
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
  signal?: AbortSignal,
): Promise<SolicitationTurnResponse> {
  const options: RequestInit = {
    method: 'POST',
    body: JSON.stringify(payload),
  }
  if (signal !== undefined) {
    options.signal = signal
  }
  return apiRequest<SolicitationTurnResponse>(
    `/solicitations/${encodeURIComponent(solicitationId)}/messages`,
    options,
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
