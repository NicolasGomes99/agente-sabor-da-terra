# Desenvolvimento

## Stack

- Frontend com React, TypeScript, React Router, Vite e npm. O Oxlint faz o lint. Os testes usam Vitest, React Testing Library e jsdom.
- Backend com Python 3.12 ou superior e uv. A API usa FastAPI e Pydantic. O acesso ao PostgreSQL usa SQLAlchemy assíncrono e asyncpg, com migrações pelo Alembic. A autenticação usa JWT e a API usa Argon2 para gerar hashes de senha. Pytest, Ruff e Testcontainers ficam no grupo `dev`. Os agentes serão desenvolvidos com Google ADK.

## Estrutura do repositório

```text
frontend/
  src/
    app/         # rotas da SPA
    components/  # componentes compartilhados
    features/    # páginas, componentes e lógica de cada funcionalidade
    lib/         # cliente HTTP e utilitários compartilhados
    styles/      # estilos globais e tokens visuais
  tests/
backend/
  api/
    app.py
    config.py
    database.py
    models/
    repositories/
    schemas/
    services/
    routers/
    dependencies.py
    agents/
  alembic.ini
  alembic/
    versions/
  tests/
    unit/
    integration/
compose.yaml
```

Os routers recebem as requisições e delegam aos serviços. Os schemas definem a entrada e a saída da API. Os serviços aplicam as regras da aplicação e usam repositories para acessar o banco. Os repositories recebem uma sessão do SQLAlchemy e operam sobre os models. `dependencies.py` liga essas camadas e fornece `get_current_user` para as rotas internas que precisarem de autenticação. Use nomes em inglês no código, como `User` para a classe e `users` para a tabela.

A estrutura prevista em `agents/` tem o orquestrador em `agent.py`, que expõe o `root_agent`, e os agentes especializados em `triage/` e `consultation/`. No chat livre, o orquestrador encaminha a conversa conforme a intenção. Nas tarefas da fila de triagem, o backend já indica o fluxo. A escolha do modelo de IA está em aberto.

## Ambiente local

Suba uma instância local do PostgreSQL separadamente enquanto o Compose e os Dockerfiles estão em preparação.

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Conexão do backend e do Alembic com o PostgreSQL, no formato `postgresql+asyncpg://usuario:senha@localhost:5432/banco`. |
| `JWT_SECRET_KEY` | Chave usada pela API para assinar e validar os tokens. |
| `CORS_ALLOWED_ORIGINS` | Origens da SPA aceitas pela API, separadas por vírgulas. Em desenvolvimento, use a origem aberta no navegador, como `http://localhost:5173`. |
| `VITE_API_URL` | URL da API usada pela SPA. O padrão é `http://localhost:8000`. |

Em `backend/`, rode `uv sync`, aplique as migrações com `uv run alembic upgrade head` e suba a API com `uv run uvicorn api.app:app --reload`. Em `frontend/`, rode `npm ci` e `npm run dev`.

Quando um model mudar o esquema do banco, gere uma revisão em `backend/` com `uv run alembic revision --autogenerate -m "describe schema change"`. Confira as operações geradas, valide o `upgrade` e o `downgrade` em um banco descartável e inclua a migração no mesmo pull request do model.

## Verificações

- Em `backend/`, rode `uv run ruff check .` e `uv run pytest`. Os testes de integração usam PostgreSQL via Testcontainers e precisam do Docker em execução.
- Em `frontend/`, rode `npm run lint`, `npm test` e `npm run build`. O build também verifica os tipos do TypeScript.

## Publicação

Na nuvem, o build estático da SPA será publicado no Firebase Hosting. A API e os agentes serão publicados juntos no Cloud Run e usarão o PostgreSQL do Cloud SQL. [Infraestrutura](infra.md)

## Entrega por funcionalidade

Organize o trabalho por fluxo de uso. A issue descreve o resultado esperado e os critérios de aceitação. O pull request reúne as mudanças necessárias para executar e verificar aquele fluxo, incluindo migração, API e interface quando fizerem parte da entrega.

O login foi a primeira entrega nesse formato. A migração cria `users`, `POST /auth/login` valida as credenciais e emite o JWT, e a tela abre `/chat` após o login. Para conferir o fluxo no navegador, cadastre um usuário de teste com `AuthService.hash_password()` e tente entrar com a senha correta e com a senha errada. A proteção de cada rota interna entra na entrega da funcionalidade que a usa. [US01](user-stories.md#us01---acessar-a-plataforma)
