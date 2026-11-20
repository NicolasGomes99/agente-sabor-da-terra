## Ambiente local

### Execução com Docker Compose

O Docker Compose disponibiliza o ambiente local completo, composto por:

- PostgreSQL 16 com suporte a pgvector.
- Backend FastAPI com os agentes de IA.
- Frontend React.
- Volumes persistentes para o banco de dados e o armazenamento documental.

As migrações do Alembic são aplicadas automaticamente antes da inicialização da API.

#### Pré-requisitos

- Docker com Docker Compose v2.
- Chave de API do Gemini Developer API.

#### Configuração

Na raiz do repositório, copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Configure as variáveis no arquivo `.env`:

| Variável | Uso |
| --- | --- |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL local. |
| `JWT_SECRET_KEY` | Chave utilizada para assinar e validar tokens JWT. |
| `GOOGLE_API_KEY` | Chave de acesso ao Gemini Developer API. |
| `GEMINI_AGENT_MODEL` | Modelo utilizado pelos agentes de IA. |

Para o ambiente de demonstração, foi validado o modelo `gemini-3.1-flash-lite`.

Utilize uma chave JWT aleatória e não versione o arquivo `.env`.

#### Inicialização

```bash
docker compose up --build -d
```

Confira o estado dos serviços:

```bash
docker compose ps
```

| Serviço | Endereço |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Documentação da API | http://localhost:8000/docs |

O PostgreSQL é acessível internamente pela rede do Compose, no serviço `db`, porta `5432`.

#### Criação do usuário

```bash
docker compose exec backend python create_dev_user.py
```

Informe o e-mail e uma senha com pelo menos 12 caracteres. Utilize essas credenciais para acessar a aplicação.

#### Carga da base Facepe

Execute a carga operacional:

```bash
docker compose exec backend python scripts/load_facepe.py
```

Para processar os pedidos de demonstração e gerar os cartões de triagem:

```bash
docker compose exec backend python scripts/load_facepe_solicitations.py
```

A carga das solicitações utiliza os agentes reais e persiste os resultados no PostgreSQL.

Consulte [Carga da base Facepe](carga-facepe.md) para conhecer os dados importados e os procedimentos de execução.

#### Atualização e manutenção

Para reconstruir os serviços após alterações no código:

```bash
docker compose up --build -d
```

Para acompanhar os logs:

```bash
docker compose logs -f backend
```

Para interromper e remover os containers:

```bash
docker compose down
```

Os volumes persistentes são preservados. Uma nova execução de `docker compose up -d` reutiliza os dados existentes.

O comando `docker compose down -v` remove também os volumes, apagando os dados persistidos. Utilize-o somente quando for necessário reinicializar completamente o ambiente.

### Execução sem Docker Compose

Também é possível executar o frontend e o backend diretamente na máquina de desenvolvimento, utilizando uma instância PostgreSQL configurada separadamente.

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Conexão do backend e do Alembic com o PostgreSQL, no formato `postgresql+asyncpg://usuario:senha@localhost:5432/banco`. |
| `JWT_SECRET_KEY` | Chave usada pela API para assinar e validar os tokens. |
| `CORS_ALLOWED_ORIGINS` | Origens da SPA aceitas pela API, separadas por vírgulas. |
| `DOCUMENT_STORAGE_BACKEND` | Armazenamento de documentos. Aceita `local` (padrão) ou `gcs`. |
| `DOCUMENT_STORAGE_DIR` | Diretório obrigatório no modo `local`. |
| `DOCUMENT_STORAGE_BUCKET` | Nome do bucket privado, obrigatório no modo `gcs`. |
| `DOCUMENT_UPLOAD_MAX_BYTES` | Limite do corpo multipart, em bytes. O padrão é 10 MiB e o máximo é 30 MiB. |
| `GEMINI_AGENT_MODEL` | Modelo utilizado pelos agentes. |
| `GOOGLE_API_KEY` | Chave de acesso ao Gemini Developer API. |
| `GOOGLE_GENAI_USE_ENTERPRISE` | Indicador de uso do ambiente Enterprise. |
| `GOOGLE_GENAI_USE_VERTEXAI` | Indicador de uso do Vertex AI. |
| `VITE_API_URL` | URL da API utilizada pela SPA. O padrão é `http://localhost:8000`. |

Configure as variáveis do backend em `backend/.env` ou no ambiente do processo.

Em `backend/`, execute:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn api.app:app --reload
```

Em `frontend/`, execute:

```bash
npm ci
npm run dev
```

Para utilizar a interface de desenvolvimento do Google ADK, execute em `backend/`:

```bash
uv run adk web api
```

A configuração das credenciais dos agentes depende da modalidade de acesso ao Gemini. O Gemini Developer API utiliza uma chave de API, enquanto o Vertex AI utiliza Application Default Credentials (ADC), que podem ser configuradas localmente com `gcloud auth application-default login`.

Não misture as configurações das modalidades de acesso nem inclua credenciais em arquivos versionados. Consulte [Infraestrutura](infra.md#configuração-dos-agentes).

### Migrações

Quando um model alterar o esquema do banco, gere uma revisão em `backend/`:

```bash
uv run alembic revision --autogenerate -m "describe schema change"
```

Confira as operações geradas, valide o `upgrade` e o `downgrade` em um banco descartável e inclua a migração no mesmo pull request do model.