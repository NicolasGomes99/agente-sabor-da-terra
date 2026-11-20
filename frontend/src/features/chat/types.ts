
export interface ChatSession {
  id: string
  title: string
  created_at: string
}

export interface Citation {
  message_id: string
  chunk_id: string
  document_id: string
  document_name: string
  chunk_content: string
  record_id: string | null
  record_fields: Record<string, string> | null
  source_type: 'record' | 'excerpt'
  label: string
  view_url: string
  download_url: string
}

export interface ChatMessage {
  id: string
  role: string
  content: string
  position: number
  created_at: string
  citations: Citation[]
}

export interface RecoverableOperation {
  operation_id: string
  status: 'processing' | 'failed'
  user_message_id: string
  content: string
  attempt: number
  error_detail: string | null
  created_at: string
  updated_at: string
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[]
  pending_operation?: RecoverableOperation | null
}

export interface CreateMessagePayload {
  content: string
  operation_id?: string
  retry?: boolean
}

export interface ChatTurnResponse {
  operation_id: string
  selected_flow: 'triage' | 'consultation'
  user_message: ChatMessage
  assistant_message: ChatMessage
}
