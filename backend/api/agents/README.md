# Camada de Agentes (`api.agents`)

Este pacote implementa a camada multiagente da Cooperativa Sabor da Terra com Google ADK.

## Ponto de Entrada da Aplicação

A aplicação backend (rotas FastAPI de chat e fila de triagem) utiliza **`orchestrate_request`** como ponto de entrada oficial.

- **Caminho de importação principal:**
  ```python
  from api.agents.agent import orchestrate_request
  # ou
  from api.agents import orchestrate_request
  ```
- **`root_agent` (`api.agents.agent.root_agent`):**
  Mantido em `api/agents/agent.py` exclusivamente para compatibilidade com a CLI e a interface de desenvolvimento do Google ADK (`uv run adk web api`).

## Contratos de Entrada e Retorno

### Entrada: `OrchestratorRequest` (`api.agents.schemas.OrchestratorRequest`)

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `session_id` | `str` | Identificador único da sessão de conversa. |
| `message_text` | `str` | Texto enviado pelo funcionário no chat ou mensagem da fila de triagem. |
| `flow` | `OrchestratorFlow` (`"auto"`, `"triage"`, `"consultation"`) | `"auto"` (padrão) usa o classificador semântico no chat livre com fallback heurístico; `"triage"` e `"consultation"` acionam diretamente o especialista indicado pelo backend. |
| `received_at` | `datetime \| date \| str \| None` | Data/hora da mensagem ou da interação/consulta. Na continuação de uma triagem em andamento, a data da mensagem em análise é preservada; ao iniciar a análise de uma nova mensagem na mesma sessão, a referência temporal é atualizada para a nova mensagem. |
| `message_received_at` | `datetime \| date \| str \| None` | Data/hora original de recebimento da mensagem em análise quando informada separadamente da data da interação no chat. |
| `is_new_triage_message` | `bool \| None` | Indica explicitamente se o turno inicia uma nova análise (`True`) ou continua a análise atual (`False`); quando `None`, o orquestrador detecta automaticamente por `source_id`, `message_received_at` ou intenção do texto. |
| `sender`, `buyer_name`, `channel`, `source_id` | `str \| None` | Metadados opcionais do canal de entrada para a triagem. |
| `sources` | `list[ConsultationSourceItem]` | Trechos documentais (`DocumentChunk`) e registros recuperados por busca para consultas documentais. |
| `financial_records` | `list[ConsultationSourceItem] \| None` | Coleção exaustiva de registros de `financeiro.csv` indexados no RAG para resumos financeiros (alternativa ou complemento ao parâmetro `financial_records_provider` de `orchestrate_request`). |
| `producer_id`, `period_start`, `period_end`, `financial_reference_date` | `str \| date \| datetime \| None` | Parâmetros opcionais de produtor, período e data de referência do cálculo financeiro (também extraíveis de consultas em linguagem natural, distintos da data da interação). |
| `history` | `list[ConversationTurn]` | Histórico prévio da sessão aberta, enviado em bloco separado do texto da mensagem em análise. |

### Retorno: `OrchestratorResponse` (`api.agents.schemas.OrchestratorResponse`)

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `session_id` | `str` | Identificador da sessão atendida. |
| `selected_flow` | `Literal["triage", "consultation"]` | Fluxo especialista que processou a solicitação. |
| `selected_agent` | `Literal["triage_agent", "consultation_agent"]` | Nome do agente especialista acionado. |
| `result` | `TriageAnalysis \| ConsultationResponse` | Saída estruturada e validada do especialista (`TriageAnalysis` em `api.agents.triage.schemas` ou `ConsultationResponse` em `api.agents.consultation.schemas`). |
| `session_history` | `list[ConversationTurn]` | Histórico atualizado da sessão atual (preservando `received_at` e `flow` por turno). |

## Camada de Integração com a Aplicação (`#50`)

Os componentes de compatibilização, reconstrução de contexto persistido, conversão de retornos e persistência transacional ficam em:

- **Contratos e protocolos:** `api.schemas.agent_integration`
- **Conversores e serviço reutilizável:** `api.services.agent_integration` (`AgentIntegrationService`)
- **Injeção FastAPI:** `api.dependencies.get_agent_integration_service`

### 1. Metadados conversacionais persistidos em `chat_messages`

Para reconstruir o contexto da conversa a partir do PostgreSQL sem depender do estado em memória (`OrchestratorSessionStore`), `ChatMessage` persiste as seguintes colunas opcionais (mantidas `NULL` para registros legados):

| Coluna | Tipo | Finalidade |
| --- | --- | --- |
| `flow` | `VARCHAR(32)` (`'triage'` \| `'consultation'` \| `NULL`) | Fluxo executado no turno. |
| `reference_received_at` | `TIMESTAMPTZ` (`NULL`) | Referência temporal do turno (data original de recebimento na triagem ou data de referência da consulta). |
| `source_id` | `VARCHAR(255)` (`NULL`) | Identificador externo da mensagem original na triagem (ex.: `PED-2026-003`). |
| `context_metadata` | `JSON` (`NULL`) | Metadados estruturados auxiliares (`sender`/`channel` na origem da triagem; resumo estruturado de `TriageAnalysis` ou `ConsultationResponse`). |

### 2. Contrato de fornecimento de fontes documentais (RAG `#52`)

O serviço de recuperação documental implementa o protocolo `DocumentSourceProvider`:

```python
from api.schemas.agent_integration import (
    DocumentRetrievalContext,
    DocumentSourceProvider,
    RetrievedDocumentSources,
)
from api.services.agent_integration import document_chunks_to_source_items


class RagDocumentSourceProvider(DocumentSourceProvider):
    async def retrieve_sources(
        self,
        context: DocumentRetrievalContext,
    ) -> RetrievedDocumentSources:
        chunks = ...  # DocumentChunk com relationship `.document` carregado
        financial_chunks = ...  # Coleção exaustiva de financeiro.csv quando aplicável
        return RetrievedDocumentSources(
            sources=document_chunks_to_source_items(chunks),
            financial_records=document_chunks_to_source_items(financial_chunks),
        )
```

Cada `DocumentChunk` convertido por `document_chunk_to_source_item()` preserva `source_id = str(chunk.id)`, `document_id = str(chunk.document_id)`, `document_name = chunk.document.original_filename`, `record_id`, `record_fields` e `source_kind`.

### 3. Exemplo de uso pelos serviços de chat (`#51`)

#### Chat livre

```python
from api.agents import orchestrate_request
from api.repositories.chat import ChatRepository
from api.services.agent_integration import AgentIntegrationService

integration = AgentIntegrationService(
    ChatRepository(db_session),
    source_provider=source_provider,
)

# 1. Prepara OrchestratorRequest reconstruindo o histórico do PostgreSQL
#    (exclude_message_id evita duplicar a mensagem atual se já tiver sido gravada)
request, retrieved = await integration.prepare_free_chat_input(
    session_id=chat.id,
    message_text=user_text,
    interaction_at=now_pe,
    exclude_message_id=user_message.id,
)

# 2. Executa o orquestrador sem depender de estado em memória
orchestrator_response = await orchestrate_request(request)

# 3. Converte o retorno e persiste resposta + citações autorizadas na mesma transação
agent_message, prepared = await integration.persist_orchestrator_response(
    session_id=chat.id,
    orchestrator_response=orchestrator_response,
    provided_sources=retrieved.all_provided_sources,
    original_request=request,
)
```

#### Continuação no chat da triagem

```python
from api.schemas.agent_integration import PreparedTriageContext

request, retrieved = await integration.prepare_triage_chat_input(
    session_id=solicitation.session_id,
    message_text=clarification_text,
    interaction_at="2026-11-19T14:00:00-03:00",
    # Opcional: se já persistido na triagem inicial, a data original (ex.: 28/10/2026)
    # é recuperada automaticamente do PostgreSQL; também pode ser informada explicitamente
    # via PreparedTriageContext (ex.: a partir de EntradaRecebida da #39).
    triage_context=PreparedTriageContext(solicitation_id=solicitation.id),
    exclude_message_id=user_message.id,
)
# request.message_received_at preserva 2026-10-28; request.received_at registra 2026-11-19.
```

- Para compor a persistência da resposta do assistente com a atualização do cartão de `Solicitation` na mesma transação (prevista na `#51`), passe `commit=False` a `persist_agent_response()` / `persist_orchestrator_response()`.
- Citações cuja fonte (`chunk_id`) não tenha sido disponibilizada ao agente na consulta são descartadas em `rejected_source_ids` e nunca são persistidas em `citations`.
- Qualquer falha na gravação da mensagem ou de uma citação desfaz a transação, preservando intacto o histórico anterior.
