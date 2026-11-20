
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

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[]
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
