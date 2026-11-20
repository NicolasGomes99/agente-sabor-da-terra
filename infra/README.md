# Infraestrutura

Os scripts desta pasta automatizam o provisionamento, as migrações, a publicação e o desprovisionamento do ambiente Google Cloud e Firebase do Sabor da Terra, conforme a issue #49.

A arquitetura, as decisões técnicas e as características dos recursos estão documentadas em [docs/infra.md](../docs/infra.md).

## Estrutura

| Arquivo | Responsabilidade |
| --- | --- |
| `config.example.json` | Modelo de configuração do ambiente |
| `config.local.json` | Configuração local não versionada |
| `common.py` | Validação, execução de comandos e proteção de segredos |
| `cloudsql.py` | Gerenciamento do Cloud SQL Auth Proxy e execução SQL |
| `hosting.py` | Configuração e publicação do Firebase Hosting |
| `provision.py` | Provisionamento dos recursos cloud |
| `migrate.py` | Execução e verificação das migrações Alembic |
| `deploy.py` | Construção e publicação da aplicação |
| `destroy.py` | Desprovisionamento do ambiente |
| `tests/` | Testes automatizados dos scripts |

## Pré-requisitos

Instale e disponibilize no PATH:

- Git;
- Python 3.12;
- uv;
- Docker com suporte a imagens Linux AMD64;
- Node.js e npm, em versões compatíveis com o frontend;
- Google Cloud CLI;
- Firebase CLI;
- Cloud SQL Auth Proxy v2.

Verifique as instalações:

```bash
git --version
uv --version
docker version
node --version
npm --version
gcloud version
firebase --version
cloud-sql-proxy --version
```

Todos os comandos deste documento devem ser executados a partir da raiz do repositório, salvo indicação contrária.

Os scripts utilizam dependências Python já presentes no backend, incluindo SQLAlchemy, Alembic e asyncpg. Não é necessário instalar o cliente `psql`.

Prepare o ambiente Python:

```bash
uv sync --project backend --locked
```

## Autenticação

Autentique-se na Google Cloud CLI:

```bash
gcloud auth login
```

Configure as Application Default Credentials utilizadas pelo Cloud SQL Auth Proxy:

```bash
gcloud auth application-default login
```

Autentique-se na Firebase CLI:

```bash
firebase login
```

Utilize contas autorizadas a administrar o projeto dedicado e a conta de faturamento selecionada.

Não crie nem utilize arquivos JSON de chaves de contas de serviço para executar os scripts.

A aplicação publicada utiliza a identidade da conta de serviço associada ao Cloud Run.

## Configuração local

Copie o arquivo de exemplo:

```bash
cp infra/config.example.json infra/config.local.json
```

Preencha os campos de acordo com o ambiente desejado.

| Campo | Descrição |
| --- | --- |
| `project_id` | Identificador globalmente único do projeto dedicado |
| `billing_account_id` | Conta de faturamento autorizada |
| `region` | Região dos recursos cloud |
| `database` | Configuração do PostgreSQL |
| `artifacts` | Repositório de imagens Docker |
| `storage` | Configuração do bucket de documentos |
| `cloud_run` | Configuração do serviço de execução |
| `inference` | Modalidade e modelo de inferência |
| `budget` | Orçamento mensal e limites de notificação |

A configuração local não deve conter senhas, tokens, chaves de API ou credenciais JSON.

O arquivo `config.local.json` é ignorado pelo Git.

### Faturamento

Liste as contas de faturamento disponíveis:

```bash
gcloud billing accounts list
```

Consulte a moeda da conta selecionada:

```bash
gcloud billing accounts describe BILLING_ACCOUNT_ID \
  --format="value(currencyCode)"
```

Configure `budget.currency` com a moeda correspondente e `budget.amount` com o valor mensal desejado.

O orçamento inicial deve corresponder aproximadamente a US$ 1,00. Para contas em outras moedas, defina manualmente o valor equivalente.

Os alertas são configurados em 50%, 80% e 100% do orçamento.

O orçamento não constitui um limite rígido de gastos e não impede cobranças adicionais.

### Inferência

O campo `inference.mode` deve ser definido explicitamente.

As modalidades disponíveis são:

- `developer`: Gemini Developer API, utilizando uma chave de API;
- `vertex`: Vertex AI, utilizando Application Default Credentials e a identidade do Cloud Run.

Antes de selecionar uma modalidade, verifique:

- disponibilidade do modelo configurado;
- preços e cotas;
- elegibilidade para utilização gratuita;
- condições de tratamento dos dados enviados ao modelo.

Não existe fallback automático entre as modalidades.

Para a Developer API, utilize uma chave dedicada ao ambiente, restrita à API necessária. A chave será solicitada pelo script durante o provisionamento, caso ainda não exista uma versão habilitada no Secret Manager.

Também é possível fornecê-la temporariamente pela variável de ambiente `GEMINI_API_KEY`.

Não registre a chave no arquivo de configuração, no histórico de comandos ou no repositório.

A utilização da Vertex AI ou da Developer API em modalidades pagas exige autorização explícita do responsável pelo ambiente.

## Testes automatizados

Execute os testes de infraestrutura:

```bash
uv run --project backend pytest -c backend/pyproject.toml infra/tests -q
```

Os testes utilizam mocks para simular os comandos externos e não devem provisionar, modificar ou excluir recursos reais.

A suíte verifica, entre outros aspectos:

- validação das configurações;
- sanitização de segredos;
- tratamento de falhas das CLIs;
- configuração de identidades e permissões;
- configuração dos recursos cloud;
- geração das instruções SQL;
- gerenciamento do Cloud SQL Auth Proxy;
- ordem das operações;
- interrupção diante de falhas;
- confirmação de operações destrutivas.

Antes da publicação, execute também os testes do backend e do frontend conforme a documentação de desenvolvimento.

A aprovação dos testes automatizados não substitui a validação do ambiente real.

## Provisionamento

Execute:

```bash
uv run --project backend python infra/provision.py
```

O script realiza as seguintes operações:

1. Valida as dependências e a configuração local.
2. Identifica a conta Google Cloud ativa e verifica a disponibilidade de ADC.
3. Cria ou identifica o projeto dedicado.
4. Vincula a conta de faturamento autorizada.
5. Habilita as APIs iniciais.
6. Cria ou verifica o orçamento mensal.
7. Configura as contas de serviço, permissões e segredos.
8. Configura a modalidade de inferência.
9. Provisiona o Cloud SQL PostgreSQL.
10. Configura o banco, os usuários, os privilégios e a extensão pgvector.
11. Provisiona o Artifact Registry.
12. Provisiona o bucket privado de documentos.
13. Associa o Firebase ao projeto e configura o site padrão do Hosting.

As principais operações que criam recursos ou vinculam faturamento exigem confirmação.

O provisionamento pode ser executado novamente para completar operações interrompidas, preservando os recursos e segredos existentes quando compatíveis com a configuração.

Recursos existentes com características incompatíveis não são modificados automaticamente.

O script não implementa rollback automático. Caso uma operação falhe, os recursos criados anteriormente poderão permanecer ativos e gerar cobranças.

Se a criação do site padrão do Firebase Hosting falhar, verifique a configuração do projeto no Firebase Console antes de executar novamente o provisionamento.

### Contas de serviço

São utilizadas três identidades:

- `sabor-da-terra-api`: backend e agentes;
- `sabor-da-terra-tasks`: identidade reservada ao processamento assíncrono;
- `sabor-da-terra-scheduler`: identidade reservada aos acionamentos agendados.

A criação das filas, dos agendamentos e das respectivas integrações pertence à issue #39.

### Segredos

O provisionamento gerencia os seguintes segredos:

| Segredo | Finalidade |
| --- | --- |
| `database-url` | Conexão do backend com o PostgreSQL |
| `database-admin-password` | Administração do PostgreSQL |
| `database-migrator-password` | Execução das migrações |
| `jwt-secret-key` | Assinatura dos tokens de autenticação |
| `gemini-api-key` | Autenticação na Gemini Developer API, quando utilizada |

O backend recebe apenas os segredos necessários à sua execução.

As credenciais administrativas e de migração não são disponibilizadas ao container da aplicação.

## Migrações

Para executar exclusivamente as migrações:

```bash
uv run --project backend python infra/migrate.py
```

O script:

1. Verifica se o repositório está em um estado limpo.
2. Identifica a revisão head do Alembic.
3. Obtém as credenciais do usuário migrador.
4. Inicia temporariamente o Cloud SQL Auth Proxy.
5. Executa `alembic upgrade head`.
6. Verifica a revisão efetivamente registrada no banco.
7. Encerra o proxy.

A conexão utiliza o proxy restrito à interface de loopback.

O usuário migrador possui permissões de alteração do schema, enquanto o usuário da aplicação possui permissões destinadas às operações de execução do sistema.

As migrações também são executadas automaticamente pelo script de deploy antes da publicação de uma nova revisão do backend.

Não são executadas durante a inicialização do container.

Em caso de falha, investigue a causa antes de continuar. O script não realiza downgrade automático.

## Deploy

Antes de publicar:

- conclua o provisionamento;
- execute os testes;
- registre as alterações em um commit;
- verifique se o Docker está em execução;
- confirme a compatibilidade das migrações com a versão anterior da aplicação;
- revise as rotas expostas publicamente.

Execute:

```bash
uv run --project backend python infra/deploy.py
```

O script realiza as seguintes operações:

1. Valida a configuração e os recursos provisionados.
2. Identifica o commit Git e a revisão head do Alembic.
3. Identifica os domínios do site padrão do Firebase Hosting.
4. Constrói a imagem Docker do backend para Linux AMD64.
5. Publica a imagem no Artifact Registry.
6. Executa e verifica as migrações.
7. Publica o backend no Cloud Run utilizando o digest da imagem.
8. Verifica a disponibilidade do backend, CORS e a proteção de um endpoint autenticado.
9. Instala as dependências e constrói o frontend com a URL do backend.
10. Publica o frontend no Firebase Hosting.
11. Verifica a disponibilidade dos domínios publicados.

As imagens são identificadas pelo hash completo do commit Git.

Uma imagem existente para o mesmo commit é reutilizada sem sobrescrever sua tag.

A publicação referencia o digest da imagem e versões específicas dos segredos.

O endereço da API é incorporado ao frontend por meio da variável `VITE_API_URL`.

Os domínios do Firebase Hosting são obtidos a partir do site padrão efetivamente associado ao projeto, sem presumir que seu identificador seja igual ao Project ID.

Ao final, são apresentados:

- commit publicado;
- revisão do banco;
- referência da imagem;
- URL do backend;
- URLs do frontend.

Caso uma etapa falhe, as etapas seguintes não serão executadas.

Não existe rollback automático do backend, do frontend ou das migrações.

## Validação funcional

Após o deploy, realize uma validação funcional do ambiente publicado.

### Autenticação

- Criar um usuário de teste utilizando o procedimento administrativo do backend.
- Acessar o frontend publicado.
- Realizar login.
- Verificar a rejeição de credenciais inválidas.
- Verificar a rejeição de requisições sem autenticação.

O script `backend/create_dev_user.py` pode ser utilizado para cadastrar o usuário inicial por meio de uma conexão local autorizada ao Cloud SQL Auth Proxy.

Utilize as credenciais do usuário de aplicação e uma conexão PostgreSQL local apropriada, sem registrar a URL de conexão ou a senha no repositório.

### Persistência

- Criar registros pela aplicação.
- Consultar os registros criados.
- Executar um novo deploy.
- Verificar se os registros continuam disponíveis.
- Confirmar a revisão Alembic e a disponibilidade da extensão pgvector.

### Documentos

- Enviar um documento pelo frontend.
- Abrir e baixar o documento.
- Verificar a integridade do conteúdo recuperado.
- Enviar documentos distintos com o mesmo nome.
- Verificar se permanecem independentes.
- Excluir um documento.
- Confirmar a remoção correspondente no bucket.
- Verificar a rejeição de acessos não autenticados.

O bucket não deve disponibilizar URLs públicas para acesso direto aos documentos.

### Agentes

A aplicação disponibiliza um endpoint temporário para validação da execução dos agentes no ambiente publicado:

```text
POST /infra/smoke-test/agents
```

O endpoint permanece desabilitado por padrão.

Para habilitá-lo temporariamente, configure a seguinte variável de ambiente no serviço Cloud Run:

```text
INFRA_SMOKE_TEST_ENABLED=true
```

A execução exige um token JWT válido e confirmação explícita de inferência.

Payload para testar o agente de triagem:

```json
{
  "flow": "triage",
  "confirm_inference": true
}
```

Payload para testar o agente de consulta:

```json
{
  "flow": "consultation",
  "confirm_inference": true
}
```

A resposta esperada contém o status da execução, o modelo utilizado, o fluxo selecionado e o agente executado.

Os testes utilizam exclusivamente dados fictícios e não dependem da integração com o RAG ou da criação de registros operacionais.

A execução pode gerar cobranças de inferência.

Após a validação, remova a variável de ambiente ou defina seu valor como `false`.

O deploy convencional substitui as variáveis de ambiente pela configuração prevista no script, mantendo o endpoint desabilitado.

### Logs

Consulte os logs recentes do backend:

```bash
gcloud run services logs read SERVICE_NAME \
  --project=PROJECT_ID \
  --region=us-central1 \
  --limit=100
```

Verifique erros relacionados a:

- inicialização da aplicação;
- conexão com o PostgreSQL;
- permissões IAM;
- acesso ao Cloud Storage;
- autenticação;
- inferência.

Não registre credenciais, tokens, conteúdo sensível de documentos ou dados pessoais desnecessários nos logs.

### Registro da validação

Registre, na issue ou no pull request correspondente, os resultados das verificações realizadas.

Inclua o commit publicado, a revisão Alembic, as URLs, os cenários executados e eventuais problemas encontrados.

Não inclua credenciais ou tokens nas evidências.

## Desprovisionamento

O desprovisionamento é uma operação destrutiva destinada exclusivamente ao projeto dedicado ao Sabor da Terra.

Antes de executá-lo:

- interrompa a utilização da aplicação;
- identifique dados que precisam ser preservados;
- exporte o banco e os documentos, quando necessário;
- verifique a integridade das exportações;
- confirme que o projeto não contém recursos de outros sistemas;
- revogue as credenciais externas dedicadas ao ambiente.

Execute:

```bash
uv run --project backend python infra/destroy.py
```

O script apresenta os recursos identificados e solicita a digitação do Project ID exato para confirmar a operação.

Após a confirmação, o script:

1. Pausa filas e agendamentos ativos na região configurada.
2. Exclui o serviço Cloud Run.
3. Remove a proteção contra exclusão do Cloud SQL.
4. Exclui a instância PostgreSQL.
5. Exclui o bucket de documentos.
6. Exclui o repositório de imagens Docker.
7. Verifica a existência de backups e buckets com exclusão reversível.
8. Remove os orçamentos gerenciados exclusivamente pelo ambiente.
9. Desvincula o faturamento do projeto.
10. Solicita a exclusão do projeto Google Cloud.

Os demais recursos associados ao projeto, incluindo Firebase Hosting, segredos e identidades, são afetados pela exclusão do projeto.

A conta Google e a conta de faturamento não são excluídas.

A exclusão do projeto pode não ser instantânea. A ausência dos recursos consultados não constitui garantia de inexistência de cobranças pendentes.

Após o desprovisionamento, verifique o Google Cloud Console e os relatórios de faturamento para identificar custos residuais ou cobranças referentes ao período anterior à exclusão.

## Configuração alternativa

Todos os scripts aceitam o argumento `--config`:

```bash
uv run --project backend python infra/provision.py \
  --config infra/config.local.json
```

Na ausência desse argumento, é utilizado `infra/config.local.json`.

## Concorrência e interrupções

Não execute operações de infraestrutura simultaneamente contra o mesmo ambiente.

Os scripts de migração, deploy e desprovisionamento utilizam o arquivo de bloqueio local:

```text
infra/operation.local.json
```

O bloqueio impede a execução simultânea dessas operações na mesma cópia do repositório.

Ele não constitui um mecanismo de bloqueio distribuído e não impede operações realizadas por outras máquinas ou diretamente pelo Google Cloud Console.

Caso uma interrupção abrupta deixe o arquivo de bloqueio no disco, confirme que não existe uma operação ativa antes de removê-lo.

## Controle de custos

O ambiente foi projetado para reduzir os custos de desenvolvimento e demonstração, sem requisitos de alta disponibilidade.

Entretanto, recursos como Cloud SQL, armazenamento, Artifact Registry, Cloud Run e inferência podem gerar cobranças.

Durante a utilização:

- acompanhe regularmente os relatórios de faturamento;
- mantenha os limites de instâncias do Cloud Run;
- evite recursos e serviços desnecessários;
- preserve as restrições de armazenamento;
- não habilite modalidades pagas de inferência sem autorização;
- desprovisione o ambiente quando ele não for mais necessário.

Em caso de falha durante o provisionamento ou o deploy, verifique quais recursos permaneceram ativos.

Os alertas de orçamento não substituem o acompanhamento do faturamento nem interrompem automaticamente o consumo.

## Segurança

- Não versione credenciais ou configurações locais.
- Não disponibilize credenciais administrativas ao backend.
- Utilize Secret Manager para os segredos da aplicação.
- Utilize identidades de serviço em vez de chaves JSON.
- Mantenha o bucket privado.
- Mantenha o acesso ao PostgreSQL mediado pelos conectores autorizados.
- Proteja os endpoints operacionais por autenticação.
- Desabilite o endpoint de smoke test após a validação.
- Restrinja as permissões IAM aos recursos necessários.
- Revogue credenciais que não são mais utilizadas.