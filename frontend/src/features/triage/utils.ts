import type { ChatMessage } from '../chat/types'

export function sortMessages(messages: ChatMessage[]): ChatMessage[] {
  return [...messages].sort((left, right) =>
    left.position - right.position ||
    left.created_at.localeCompare(right.created_at) ||
    left.id.localeCompare(right.id)
  )
}

export function uniqueMessages(messages: ChatMessage[]): ChatMessage[] {
  return [...new Map(messages.map((message) => [message.id, message])).values()]
}

export function normalizeSearch(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
}

export function requestCount(count: number): string {
  return count === 1 ? '1 solicitação' : `${count} solicitações`
}
