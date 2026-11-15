# Desenvolvimento

## Stack

- **Frontend** com React e TypeScript, Vite e npm. O Oxlint faz a análise do código. Os testes usam Vitest, React Testing Library e jsdom.
- **Backend** com Python 3.12 ou superior e uv. A API usa FastAPI e Pydantic. O acesso ao PostgreSQL usa SQLAlchemy, com migrações pelo Alembic. Os agentes usam Google ADK. Pytest e Ruff ficam no grupo `dev`.

## Estrutura do repositório

```text
frontend/
  src/
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
    agents/
  tests/
compose.yaml
```

Os models mapeiam as tabelas e os schemas definem a entrada e a saída da API. Os routers chamam os serviços, que aplicam as regras da aplicação. Os repositories recebem uma sessão do SQLAlchemy para acessar o banco. O código segue nomes em inglês, como `User` para a classe e `users` para a tabela.

A estrutura prevista em `agents/` tem o orquestrador em `agent.py`, que expõe o `root_agent`, e os agentes especializados em `triage/` e `consultation/`. No chat livre, o orquestrador encaminha a conversa conforme a intenção. Nas tarefas da fila de triagem, o backend já indica o fluxo. A escolha do modelo de IA está em aberto.

## Ambiente local e publicação

Use `uv sync` em `backend/` para preparar as dependências. Em `frontend/`, use `npm install` e `npm run dev` para rodar a SPA.

O PostgreSQL local será executado pelo Docker Compose. A URL de conexão vem de `DATABASE_URL`, e o esquema será criado com as migrações do Alembic. O Compose e os Dockerfiles ainda precisam ser configurados.

Na nuvem, o build estático da SPA será publicado no Firebase Hosting. A API e os agentes serão publicados juntos no Cloud Run e usarão o PostgreSQL do Cloud SQL. [Infraestrutura](infra.md)

## Entrega por funcionalidade

O trabalho será organizado por funcionalidade. Cada issue reúne as mudanças de backend e frontend necessárias para testar o fluxo completo em um único pull request.