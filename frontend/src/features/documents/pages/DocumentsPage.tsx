import { useEffect, useRef, useState, type FormEvent } from 'react'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { DocumentPreview } from '../components/DocumentPreview'
import { listDocuments, uploadDocument, type DocumentRecord } from '../documentsApi'
import './documents.css'

const textExtensions = new Set(['txt', 'md', 'csv', 'json'])
const mediaExtensions = new Set(['pdf', 'gif', 'jpg', 'jpeg', 'png', 'webp'])

function fileExtension(filename: string) {
  const separator = filename.lastIndexOf('.')
  return separator === -1 ? '' : filename.slice(separator + 1).toLowerCase()
}

function canPreviewDocument(filename: string) {
  const extension = fileExtension(filename)
  return textExtensions.has(extension) || mediaExtensions.has(extension)
}

type ListState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; documents: DocumentRecord[] }

export function DocumentsPage() {
  const { logout } = useAuth()
  const [state, setState] = useState<ListState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [selectedDocument, setSelectedDocument] = useState<DocumentRecord | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const uploadInProgress = useRef(false)
  const fileInput = useRef<HTMLInputElement>(null)

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

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file || state.status !== 'ready' || uploadInProgress.current) return

    uploadInProgress.current = true
    setUploading(true)
    setUploadError(null)
    try {
      const document = await uploadDocument(file)
      setState((current) => current.status === 'ready'
        ? { status: 'ready', documents: [...current.documents, document] }
        : current)
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
    } catch (error) {
      const status = error instanceof ApiError ? error.status : undefined
      switch (status) {
        case 401:
          logout()
          break
        case 413:
          setUploadError('O arquivo excede o limite de envio.')
          break
        case 422:
          setUploadError('O arquivo foi rejeitado. Selecione um arquivo válido.')
          break
        default:
          setUploadError('Não foi possível enviar o documento. Tente novamente.')
      }
    } finally {
      uploadInProgress.current = false
      setUploading(false)
    }
  }

  return (
    <AppShell>
      <section className="documents-page" aria-labelledby="documents-heading">
        <h1 id="documents-heading">Documentos</h1>
        <form className="documents-upload" onSubmit={submitUpload}>
          <div>
            <label htmlFor="document-file">Arquivo</label>
            <input
              id="document-file"
              type="file"
              ref={fileInput}
              disabled={uploading}
              onChange={(event) => {
                setFile(event.currentTarget.files?.[0] ?? null)
                setUploadError(null)
              }}
            />
          </div>
          <button type="submit" disabled={state.status !== 'ready' || !file || uploading}>
            {uploading ? 'Enviando…' : 'Enviar'}
          </button>
        </form>
        {uploadError && <p className="documents-error" role="alert">{uploadError}</p>}
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
                <li key={document.id}>
                  <span>{document.original_filename}</span>
                  {canPreviewDocument(document.original_filename) && (
                    <button type="button" onClick={() => setSelectedDocument(document)}>
                      Abrir
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )
        )}
        {selectedDocument && (
          <DocumentPreview
            key={selectedDocument.id}
            document={selectedDocument}
            asText={textExtensions.has(fileExtension(selectedDocument.original_filename))}
            onClose={() => setSelectedDocument(null)}
          />
        )}
      </section>
    </AppShell>
  )
}
