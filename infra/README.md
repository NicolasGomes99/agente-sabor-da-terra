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
