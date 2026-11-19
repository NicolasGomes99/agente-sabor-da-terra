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
| `sources` | `list[ConsultationSourceItem]` | Trechos documentais (`DocumentChunk`) e registros recuperados para consultas documentais. |
| `history` | `list[ConversationTurn]` | Histórico prévio da sessão aberta, enviado em bloco separado do texto da mensagem em análise. |

### Retorno: `OrchestratorResponse` (`api.agents.schemas.OrchestratorResponse`)

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `session_id` | `str` | Identificador da sessão atendida. |
| `selected_flow` | `Literal["triage", "consultation"]` | Fluxo especialista que processou a solicitação. |
| `selected_agent` | `Literal["triage_agent", "consultation_agent"]` | Nome do agente especialista acionado. |
| `result` | `TriageAnalysis \| ConsultationResponse` | Saída estruturada e validada do especialista (`TriageAnalysis` em `api.agents.triage.schemas` ou `ConsultationResponse` em `api.agents.consultation.schemas`). |
| `session_history` | `list[ConversationTurn]` | Histórico atualizado da sessão atual (preservando `received_at` e `flow` por turno). |
