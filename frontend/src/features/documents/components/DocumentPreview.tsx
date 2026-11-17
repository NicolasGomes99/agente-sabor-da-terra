import { useEffect, useState } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { getDocumentContent, type DocumentRecord } from '../documentsApi'

const imageTypes = new Set(['image/gif', 'image/jpeg', 'image/png', 'image/webp'])

type PreviewState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'text'; text: string }
  | { status: 'pdf' | 'image'; url: string }

export function DocumentPreview({ document, asText, onClose }: {
  document: DocumentRecord
  asText: boolean
  onClose: () => void
}) {
  const { logout } = useAuth()
  const [preview, setPreview] = useState<PreviewState>({ status: 'loading' })
  const { id, original_filename: filename } = document

  useEffect(() => {
    const controller = new AbortController()
    let url: string | undefined

    async function loadPreview() {
      try {
        const content = await getDocumentContent(id, controller.signal)
        if (controller.signal.aborted) return

        if (asText) {
          const text = await content.text()
          if (!controller.signal.aborted) setPreview({ status: 'text', text })
        } else if (content.type === 'application/pdf' || imageTypes.has(content.type)) {
          url = URL.createObjectURL(content)
          setPreview({ status: content.type === 'application/pdf' ? 'pdf' : 'image', url })
        } else {
          setPreview({ status: 'error', message: 'Este formato não pode ser visualizado.' })
        }
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }
        const message = error instanceof ApiError && error.status === 404
          ? 'O documento está indisponível.'
          : 'Não foi possível abrir o documento.'
        setPreview({ status: 'error', message })
      }
    }

    void loadPreview()
    return () => {
      controller.abort()
      if (url !== undefined) URL.revokeObjectURL(url)
    }
  }, [asText, id, logout])

  return (
    <section className="document-preview" aria-labelledby="document-preview-heading">
      <header>
        <h2 id="document-preview-heading">{filename}</h2>
        <button type="button" onClick={onClose}>Fechar</button>
      </header>
      {preview.status === 'loading' && <p role="status">Abrindo documento…</p>}
      {preview.status === 'error' && <p role="alert">{preview.message}</p>}
      {preview.status === 'text' && <pre>{preview.text}</pre>}
      {preview.status === 'pdf' && <iframe src={preview.url} title={filename} />}
      {preview.status === 'image' && <img src={preview.url} alt={filename} />}
    </section>
  )
}
