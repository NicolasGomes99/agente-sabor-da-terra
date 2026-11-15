import { AppShell } from '../../../components/layout/AppShell'
import { ChatHeader } from '../components/ChatHeader'
import { ChatHistory } from '../components/ChatHistory'
import { ChatInput } from '../components/ChatInput'
import { MessageList } from '../components/MessageList'
import './chat.css'

const messages = [
  {
    id: 'welcome',
    author: 'assistant' as const,
    text: 'Olá! Posso ajudar a consultar pedidos, produtores e documentos da cooperativa.',
  },
  {
    id: 'example',
    author: 'user' as const,
    text: 'Quais pedidos estão aguardando informações?',
  },
  {
    id: 'answer',
    author: 'assistant' as const,
    text: 'A triagem possui solicitações com pendências de prazo e documentação. O chat funcional será conectado ao backend em uma próxima etapa.',
  },
]

export function ChatPage() {
  return (
    <AppShell>
      <div className="chat-page">
        <ChatHistory
          conversations={['Visão geral da cooperativa', 'Pedidos recentes']}
        />
        <section className="chat-workspace" aria-label="Chat ilustrativo">
          <ChatHeader
            title="Novo chat"
            subtitle="Consulte informações da operação da cooperativa."
          />
          <MessageList messages={messages} />
          <ChatInput />
        </section>
      </div>
    </AppShell>
  )
}
