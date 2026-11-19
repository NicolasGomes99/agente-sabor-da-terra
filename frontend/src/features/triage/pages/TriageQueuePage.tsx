import { useEffect, useMemo, useState } from 'react'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { TriageQueueFilters } from '../components/TriageQueueFilters'
import { TriageQueueHeader } from '../components/TriageQueueHeader'
import { TriageSolicitationCard } from '../components/TriageSolicitationCard'
import { listSolicitations } from '../triageApi'
import {
  normalizeSearch,
  requestCount,
} from '../utils'
import {
  solicitationTypeLabels,
  type Solicitation,
  type SolicitationStatus,
  type SolicitationType,
  type SolicitationUrgency,
} from '../types'

import './triage.css'

type QueueState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; solicitations: Solicitation[] }

export function TriageQueuePage() {
  const { logout } = useAuth()
  const [state, setState] = useState<QueueState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<SolicitationStatus | ''>('')
  const [urgency, setUrgency] = useState<SolicitationUrgency | ''>('')
  const [type, setType] = useState<SolicitationType | ''>('')

  useEffect(() => {
    const controller = new AbortController()

    async function loadSolicitations() {
      try {
        const solicitations = await listSolicitations(controller.signal)
        if (!controller.signal.aborted) {
          setState({ status: 'ready', solicitations })
        }
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }
        setState({ status: 'error' })
      }
    }

    void loadSolicitations()
    return () => controller.abort()
  }, [attempt, logout])

  const query = normalizeSearch(search)
  const visibleSolicitations = useMemo(() => {
    if (state.status !== 'ready') return []

    return state.solicitations.filter((solicitation) => (
      (!status || solicitation.status === status) &&
      (!urgency || solicitation.urgency === urgency) &&
      (!type || solicitation.request_type === type) &&
      (
        !query ||
        normalizeSearch(
          `${solicitation.id} ${solicitation.summary} ` +
          `${solicitationTypeLabels[solicitation.request_type]}`,
        ).includes(query)
      )
    ))
  }, [query, state, status, type, urgency])

  const hasFilters = Boolean(search.trim() || status || urgency || type)

  function clearFilters() {
    setSearch('')
    setStatus('')
    setUrgency('')
    setType('')
  }

  function retry() {
    setState({ status: 'loading' })
    setAttempt((previous) => previous + 1)
  }

  return (
    <AppShell>
      <section className="triage-page" aria-labelledby="triage-heading">
        <TriageQueueHeader
          countLabel={
            state.status === 'ready'
              ? requestCount(visibleSolicitations.length)
              : 'Carregando solicitações'
          }
          onRefresh={retry}
        />

        <TriageQueueFilters
          search={search}
          status={status}
          urgency={urgency}
          type={type}
          hasFilters={hasFilters}
          onSearchChange={setSearch}
          onStatusChange={setStatus}
          onUrgencyChange={setUrgency}
          onTypeChange={setType}
          onClear={clearFilters}
        />

        {state.status === 'loading' && (
          <p role="status">Carregando solicitações…</p>
        )}
        {state.status === 'error' && (
          <div className="triage-notice error">
            <p role="alert">Não foi possível carregar a fila de triagem.</p>
            <button className="triage-button" type="button" onClick={retry}>
              Tentar novamente
            </button>
          </div>
        )}
        {state.status === 'ready' && state.solicitations.length === 0 && (
          <p className="triage-empty" role="status">
            Nenhuma solicitação na fila.
          </p>
        )}
        {state.status === 'ready' &&
          state.solicitations.length > 0 &&
          visibleSolicitations.length === 0 && (
            <div className="triage-empty">
              <p role="status">Nenhuma solicitação encontrada.</p>
              <button
                className="triage-button"
                type="button"
                onClick={clearFilters}
              >
                Limpar busca e filtros
              </button>
            </div>
          )}
        {visibleSolicitations.length > 0 && (
          <ul className="triage-grid" aria-label="Solicitações da triagem">
            {visibleSolicitations.map((solicitation) => (
              <TriageSolicitationCard
                key={solicitation.id}
                solicitation={solicitation}
              />
            ))}
          </ul>
        )}
      </section>
    </AppShell>
  )
}
