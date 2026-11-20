# Infraestrutura

Os scripts desta pasta orquestram os recursos Google Cloud definidos pela issue #49.

## Configuração local

Copie o exemplo e preencha o Project ID real:

```bash
cp infra/config.example.json infra/config.local.json
```

`infra/config.local.json` não é versionado. Não inclua senhas, tokens ou credenciais JSON nesse arquivo.

## Uso

```bash
python infra/provision.py
python infra/migrate.py
python infra/deploy.py
python infra/destroy.py
```

As operações ainda serão implementadas em blocos separados. Os comandos não usam recursos pagos até a implementação completa da operação correspondente.

## Etapa 4: projeto e faturamento

Depois de autenticar e preencher `infra/config.local.json`, execute:

```bash
python infra/provision.py
```

O script valida a conta `gcloud` ativa, cria ou identifica o projeto, exige a conta de faturamento configurada, habilita as APIs mínimas desta etapa e cria o orçamento mensal restrito ao projeto. Ele não cria Spend Caps e não ativa créditos ou planos pagos.
