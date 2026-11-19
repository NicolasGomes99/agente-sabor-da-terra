import { Link } from 'react-router-dom'

export function TriageBackLink() {
  return (
    <Link className="triage-back-link" to="/triagem">
      ← Voltar para a fila
    </Link>
  )
}
