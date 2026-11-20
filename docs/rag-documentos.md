# RAG — Indexação e Recuperação da Base Documental (#52)

Este documento descreve os procedimentos de carga inicial, processamento, indexação vetorial (`pgvector`), recuperação semântica e estruturada, configuração do modelo de embeddings e validação da base documental da Cooperativa Sabor da Terra.

---

## 1. Arquitetura e Modelos Persistidos

A indexação reutiliza os modelos `Document` e `DocumentChunk`, o serviço `DocumentService` e os adaptadores de armazenamento `LocalDocumentStorage` e `GCSDocumentStorage` (`#11`/`#12`), estendendo o esquema na migração `0012_pgvector_document_indexing`:

- **Extensão `pgvector`**: habilitada via `CREATE EXTENSION IF NOT EXISTS vector`.
- **`documents`**:
  - `source_path` (`VARCHAR(512)`, índice único parcial `uq_documents_source_path` para `source_path IS NOT NULL`): garante idempotência da carga inicial da Facepe preservando o suporte a múltiplos documentos enviados pela API com o mesmo `original_filename` (`source_path = NULL`).
  - `content_sha256` (`VARCHAR(64)`): hash SHA-256 do arquivo original preservado no storage.
  - `processing_status` (`pending | processing | indexed | failed`): controla visibilidade na recuperação (documentos pendentes ou com falha nunca entram em buscas).
  - `processing_error` (`TEXT`) e `indexed_at` (`TIMESTAMPTZ`).
- **`document_chunks`**:
  - `embedding` (`VECTOR` — `pgvector.sqlalchemy.Vector`, compatível com qualquer dimensão configurada).
  - `embedding_model` (`VARCHAR(128)`), `chunk_index` (`INTEGER`), `chunk_key` (`VARCHAR(255)`) e `is_active` (`BOOLEAN`).
  - `record_id` e `record_fields` (`JSON`): preservam integralmente identificadores de negócio e todos os campos originais das linhas de CSV sem conversões ou suposições de unidade.

---

## 2. Configuração do Modelo de Embeddings e Recuperação

Variáveis de ambiente em `backend/.env` (todas opcionais, com padrões seguros):

| Variável | Padrão | Descrição |
|---|---|---|
| `GOOGLE_API_KEY` | *(obrigatória para Gemini Developer API)* | Credencial consumida pelo `google-genai` SDK. |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Modelo utilizado pelo `GeminiEmbeddingClient`. |
| `GEMINI_EMBEDDING_DIMENSIONS` | `768` | Dimensão de saída dos vetores (`1` a `3072`), normalizados por L2. |
| `RAG_SEMANTIC_TOP_K` | `8` | Quantidade máxima padrão de resultados na busca semântica vetorial (não limita consultas estruturadas exaustivas). |
| `DOCUMENT_STORAGE_BACKEND` | `local` | Adaptador de arquivos originais (`local` ou `gcs`). |
| `DOCUMENT_STORAGE_DIR` / `DOCUMENT_STORAGE_BUCKET` | — | Diretório local ou bucket privado no Cloud Storage. |

> **Nota sobre cota gratuita (Free Tier):** `GeminiEmbeddingClient` agrupa textos em lotes e trata automaticamente respostas `429 RESOURCE_EXHAUSTED` respeitando o `retryDelay` retornado pela API.

---

## 3. Processamento e Indexação

### 3.1 Regras de extração (`backend/api/rag/extractors.py`)
- **Arquivos TXT** (certificações, laudos, inspeções, contratos e fichas técnicas): divisão orientada a seções que mantém documentos curtos íntegros e injeta o cabeçalho de contexto (título, número do documento, validade, partes/produtor) em todos os trechos de documentos mais longos.
- **Arquivos CSV**: um `DocumentChunk` por registro, preservando todos os nomes de colunas e valores originais em `record_fields` (ex.: `LOT-2026-0099` mantém `"40 maços (kg)"` integralmente) e vinculando `record_id` (`id_transacao`, `lote_id`, `id`, `produto`, etc.).

### 3.2 Carga inicial da base Facepe (`backend/scripts/load_facepe_documents.py`)
A carga é um comando explícito separado da inicialização da API e indexa os **20 documentos textuais** (`certificacoes/`, `contratos/`, `fichas_tecnicas/`) e os **5 CSVs** (`financeiro.csv`, `lotes.csv`, `produtores.csv`, `sazonalidade.csv`, `tabela_precos_outubro_2026.csv`):

```bash
cd backend
uv run alembic upgrade head
uv run python scripts/load_facepe_documents.py
```

Opções disponíveis:
- `--data-dir /caminho/para/dados`: especifica diretório alternativo (padrão: `backend/data`).
- `--reindex`: força reprocessamento de documentos já indexados preservando IDs e citações existentes.
- `--retry-failed`: reprocessa apenas documentos atualmente em estado `pending` ou `failed`.

Reexecutar o comando sem alterações mantém os documentos e trechos existentes sem duplicação e preserva todos os UUIDs e vínculos de citações.

### 3.3 Upload pela aplicação, falhas, reprocessamento e exclusão
- **`POST /documents`**: salva o arquivo original no storage, persiste `Document` e, para arquivos `.txt` e `.csv`, executa automaticamente o processamento/indexação via `DocumentIndexingService`. Se ocorrer falha na extração ou na geração de embeddings, nenhum dado parcial é persistido em `document_chunks` e o documento é marcado como `failed`.
- **`GET /documents/indexing`** (opcional `?status=pending|processing|indexed|failed`): lista o estado de processamento e contagem de trechos ativos dos documentos.
- **`POST /documents/{document_id}/reindex`**: reexecuta a indexação de um documento pendente, falhado ou já indexado sem duplicar trechos e preservando todos os trechos vinculados a citações existentes (`is_active = False` para trechos antigos citados se o conteúdo mudar).
- **`DELETE /documents/{document_id}`**: remove o documento e todos os seus trechos da base consultável quando não há citações; continua bloqueada com `409 Conflict` quando o documento possui citações.

---

## 4. Recuperação de Informações (`backend/api/rag/retrieval.py`)

`RagRetrievalService` implementa o contrato `DocumentSourceProvider` definido na `#50`, retornando `RetrievedDocumentSources` com itens `ConsultationSourceItem` (preservando `source_id = DocumentChunk.id`, `document_id`, `document_name`, `record_id` e `record_fields`):

1. **Busca semântica (`semantic_search`)**: distância de cosseno via `pgvector` (`<=>`) filtrando `documents.processing_status = 'indexed'`, `document_chunks.is_active = true` e `vector_dims(embedding) = len(query_embedding)`.
2. **Recuperação estruturada exaustiva (`get_by_record_ids`, `query_structured_records`)**: recupera **todos** os registros elegíveis por documento, identificador ou filtro de campos, sem aplicar o limite `RAG_SEMANTIC_TOP_K`.
3. **Recuperação financeira (`query_financial_records`)**: seleciona registros de `financeiro.csv` por produtor e por `data` (vendas), `data_pagamento` (pagamentos registrados) ou pendências na data de referência (`include_pending_as_of_reference=True`, incluindo períodos anteriores e excluindo outros produtores), integrando diretamente com a ferramenta determinística da `#40`.
4. **Contexto conversacional (`build_contextual_query`)**: em perguntas de acompanhamento, incorpora entidades e trechos recentes do histórico (`context.history`) para recuperar o documento ou registro discutido anteriormente.
5. **Distinção entre ausência de dados e falha**: base vazia ou consulta sem correspondência retorna lista vazia (`[]`); falhas de banco ou de geração de embeddings lançam `DocumentRetrievalError`.

---

## 5. Execução dos Testes

> Pré-requisito: Docker em execução (os testes de integração utilizam `pgvector/pgvector:pg16` via Testcontainers).

```bash
cd backend

# Testes unitários (extração TXT/CSV, metadados, embeddings e contexto conversacional)
uv run pytest tests/unit/rag

# Teste de migração pgvector (upgrade, alembic check, preservação de citações e downgrade)
uv run pytest tests/integration/migrations/test_pgvector_migration.py

# Testes de integração completos do RAG com PostgreSQL + pgvector (embeddings simulados determinísticos)
uv run pytest tests/integration/rag

# Lint
ruff check .
```

Para bancos locais em Docker, utilize a imagem `pgvector/pgvector:pg16` no lugar de `postgres:16-alpine` para habilitar a extensão `vector`.

---

## 6. Validação da Carga Completa com o Modelo Real (`gemini-embedding-001`)

Executada em **20/11/2026** sobre um banco PostgreSQL limpo (`pgvector/pgvector:pg16`) migrado até `0012_pgvector_document_indexing`, utilizando `GEMINI_EMBEDDING_MODEL=gemini-embedding-001` e `GEMINI_EMBEDDING_DIMENSIONS=768`:

- **Carga inicial:** 25 documentos criados e indexados (20 TXT + 5 CSV) em `88,10s` (incluindo espera automática de 429 do Free Tier), totalizando **202 trechos ativos**:
  - 31 trechos textuais (20 arquivos TXT)
  - 30 registros de `financeiro.csv`
  - 20 registros de `lotes.csv`
  - 18 registros de `produtores.csv`
  - 50 registros de `sazonalidade.csv`
  - 53 registros de `tabela_precos_outubro_2026.csv`
- **Reexecução da carga:** `0` criados, `25` reutilizados, `25` ignorados (idempotência completa, zero duplicações).

### Cenários avaliados e resultados obtidos

| Cenário | Consulta avaliada | Fontes esperadas | Principais fontes obtidas | Status |
|---|---|---|---|---|
| **C1 — Certificações orgânicas de mel** | *"Quais produtores tem certificacao organica vigente para mel silvestre e qual a validade?"* | Certificações orgânicas de produtores de mel (`P002`, `P018`, `P008`) e ficha técnica do mel | `mel_silvestre.txt`, `cert_organica_jose_santos_P002.txt`, `cert_organica_debora_melo_P018.txt` (`0,31s`) | Aprovado |
| **C2 — Exigências contratuais PNAE** | *"Quais sao as condicoes obrigatorias e prazo de pagamento do contrato PNAE de Garanhuns?"* | `contrato_pnae_garanhuns.txt` | `contrato_pnae_garanhuns.txt` (top 3 trechos, `0,61s`) | Aprovado |
| **C3 — Preços vigentes (out/2026)** | *"Qual o preco vigente de queijo coalho organico e o desconto de atacado em outubro de 2026?"* | `tabela_precos_outubro_2026.csv` (`queijo coalho`) | `tabela_precos_outubro_2026.csv[queijo coalho]` em 1º lugar (`0,96s`), preservando vigência e condições | Aprovado |
| **C4 — Rastreabilidade de lote** | *"Qual a origem, produtor, produto, quantidade e pedido historico do lote LOT-2026-0094?"* | `lotes.csv` (`LOT-2026-0094`) | `lotes.csv[LOT-2026-0094]` em 1º lugar (`0,32s`) com todos os campos originais | Aprovado |
| **C5 — Unidade ambígua preservada** | *"Quais os dados e observacao original do lote LOT-2026-0099?"* | `lotes.csv` (`LOT-2026-0099`, `"40 maços (kg)"`) | `lotes.csv[LOT-2026-0099]` em 1º lugar (`0,36s`) com `observacao = '40 maços (kg)'` intacto | Aprovado |
| **C6 — Inspeção sanitária ADAGRO** | *"Qual produtor apresentou nao conformidade grave por falta de registro SIE na inspecao da ADAGRO?"* | `inspecao_adagro_2026.txt` | `inspecao_adagro_2026.txt` (top 3 trechos, `0,54s`) | Aprovado |
| **C7 — Acompanhamento conversacional** | *"E qual e a data de validade dessa certificacao?"* (após turno sobre `P001`) | `cert_organica_maria_silva_P001.txt` e `produtores.csv[P001]` | `produtores.csv[P001]` e `cert_organica_maria_silva_P001.txt` no topo (`0,35s`) | Aprovado |
| **C8 — Consultas financeiras estruturadas** | Vendas `P001` set/2026; pagamentos `P001` out/2026; pendências `P003` em 31/10/2026 | `FIN-2026-001/002/015`; `FIN-2026-001/002`; `FIN-2026-013/014` | Exato: vendas `['FIN-2026-001', 'FIN-2026-002', 'FIN-2026-015']`, pagamentos `['FIN-2026-001', 'FIN-2026-002']`, pendências `['FIN-2026-013', 'FIN-2026-014']` | Aprovado |
