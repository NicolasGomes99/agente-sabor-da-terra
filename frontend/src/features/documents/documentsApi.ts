import { apiRequest, apiRequestBlob } from '../../lib/api-client'

export interface DocumentRecord {
  id: string
  original_filename: string
}

export function listDocuments(signal?: AbortSignal): Promise<DocumentRecord[]> {
  return apiRequest<DocumentRecord[]>('/documents', { signal })
}

export function uploadDocument(file: File): Promise<DocumentRecord> {
  const body = new FormData()
  body.append('file', file)
  return apiRequest<DocumentRecord>('/documents', { method: 'POST', body })
}

export function getDocumentContent(id: string, signal?: AbortSignal): Promise<Blob> {
  return apiRequestBlob(`/documents/${encodeURIComponent(id)}/content`, { signal })
}

export function downloadDocument(id: string): Promise<Blob> {
  return apiRequestBlob(`/documents/${encodeURIComponent(id)}/download`)
}

export function deleteDocument(id: string): Promise<void> {
  return apiRequest<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
