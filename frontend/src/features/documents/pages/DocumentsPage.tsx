import { useEffect, useState } from 'react'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { listDocuments, type DocumentRecord } from '../documentsApi'
import './documents.css'

type ListState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; documents: DocumentRecord[] }

export function DocumentsPage() {
  const { logout } = useAuth()
  const [state, setState] = useState<ListState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    async function loadDocuments() {
      try {
        const documents = await listDocuments(controller.signal)
        if (!controller.signal.aborted) {
          setState({ status: 'ready', documents })
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

    void loadDocuments()
    return () => controller.abort()
  }, [attempt, logout])

  function retry() {
    setState({ status: 'loading' })
    setAttempt((previous) => previous + 1)
  }

  return (
    <AppShell>
      <section className="documents-page" aria-labelledby="documents-heading">
        <h1 id="documents-heading">Documentos</h1>
        {state.status === 'loading' && <p role="status">Carregando documentos…</p>}
        {state.status === 'error' && (
          <div className="documents-error">
            <p role="alert">Não foi possível carregar os documentos.</p>
            <button type="button" onClick={retry}>Tentar novamente</button>
          </div>
        )}
        {state.status === 'ready' && (
          state.documents.length === 0 ? (
            <p role="status">Nenhum documento cadastrado.</p>
          ) : (
            <ul className="documents-list" aria-label="Arquivos cadastrados">
              {state.documents.map((document) => (
                <li key={document.id}>{document.original_filename}</li>
              ))}
            </ul>
          )
        )}
      </section>
    </AppShell>
  )
}
