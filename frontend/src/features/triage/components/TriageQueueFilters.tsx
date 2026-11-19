import {
  solicitationStatusLabels,
  solicitationTypeLabels,
  solicitationUrgencyLabels,
  type SolicitationStatus,
  type SolicitationType,
  type SolicitationUrgency,
} from '../types'

const statusOptions = Object.keys(
  solicitationStatusLabels,
) as SolicitationStatus[]
const typeOptions = Object.keys(
  solicitationTypeLabels,
) as SolicitationType[]
const urgencyOptions = Object.keys(
  solicitationUrgencyLabels,
) as SolicitationUrgency[]

interface TriageQueueFiltersProps {
  search: string
  status: SolicitationStatus | ''
  urgency: SolicitationUrgency | ''
  type: SolicitationType | ''
  hasFilters: boolean
  onSearchChange: (value: string) => void
  onStatusChange: (value: SolicitationStatus | '') => void
  onUrgencyChange: (value: SolicitationUrgency | '') => void
  onTypeChange: (value: SolicitationType | '') => void
  onClear: () => void
}

export function TriageQueueFilters({
  search,
  status,
  urgency,
  type,
  hasFilters,
  onSearchChange,
  onStatusChange,
  onUrgencyChange,
  onTypeChange,
  onClear,
}: TriageQueueFiltersProps) {
  return (
    <div className="triage-filters" aria-label="Busca e filtros da triagem">
      <div className="triage-filter-field triage-search-field">
        <label htmlFor="triage-search">Buscar solicitações</label>
        <input
          id="triage-search"
          type="search"
          value={search}
          placeholder="Resumo, tipo ou identificador"
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>
      <div className="triage-filter-field">
        <label htmlFor="triage-status">Estado</label>
        <select
          id="triage-status"
          value={status}
          onChange={(event) => {
            onStatusChange(event.target.value as SolicitationStatus | '')
          }}
        >
          <option value="">Todos</option>
          {statusOptions.map((value) => (
            <option key={value} value={value}>
              {solicitationStatusLabels[value]}
            </option>
          ))}
        </select>
      </div>
      <div className="triage-filter-field">
        <label htmlFor="triage-urgency">Urgência</label>
        <select
          id="triage-urgency"
          value={urgency}
          onChange={(event) => {
            onUrgencyChange(event.target.value as SolicitationUrgency | '')
          }}
        >
          <option value="">Todas</option>
          {urgencyOptions.map((value) => (
            <option key={value} value={value}>
              {solicitationUrgencyLabels[value]}
            </option>
          ))}
        </select>
      </div>
      <div className="triage-filter-field">
        <label htmlFor="triage-type">Tipo</label>
        <select
          id="triage-type"
          value={type}
          onChange={(event) => {
            onTypeChange(event.target.value as SolicitationType | '')
          }}
        >
          <option value="">Todos</option>
          {typeOptions.map((value) => (
            <option key={value} value={value}>
              {solicitationTypeLabels[value]}
            </option>
          ))}
        </select>
      </div>
      <button
        className="triage-button triage-clear-filters"
        type="button"
        onClick={onClear}
        disabled={!hasFilters}
      >
        Limpar
      </button>
    </div>
  )
}
