# Protótipo navegável da Sabor da Terra

## Executar

Abra `index.html` no navegador ou execute o comando na raiz do repositório.

```bash
python -m http.server 8000 --directory docs/prototype
```

Se usar o servidor estático, acesse `http://localhost:8000`. A senha de demonstração é `demo`. O navegador simula o assistente e os canais com exemplos adaptados da base fornecida.

## Roteiro rápido

1. Na **Triagem**, localize `PED-2026-003`. O cartão mostra **Recebida** até você abrir o chat, quando a solicitação passa para **Em análise**. Confira a data original de entrega e a pendência no chat. Informe `20/11/2026` para atualizar o rascunho. A pendência deixa de aparecer como aberta e a solicitação segue **Em análise**. Use **Revisar pedido** para cadastrar e abrir o pedido, que mostra a solicitação de origem.
2. Abra `PED-2026-004` para ver a pendência de DAP ou CAF e a fonte citada. Use **Revisar pedido** e mantenha o intervalo de `20/11/2026` a `24/11/2026`. No pedido salvo, tente alocar 5 potes de mel ao produtor inativo e confira o bloqueio. Selecione um produtor ativo, marque a confirmação de disponibilidade e salve a alocação. Na **Triagem**, use **Encerrar**, registre o resultado e reabra o chat para conferir o estado **Finalizada**.
3. Em **Novo chat**, pergunte por `LOT-2026-0094` para abrir a citação e baixar a fonte, ou use **Sugerir produtor de tomate** para ver a capacidade estimada. Para testar o resumo financeiro, peça “Gere um resumo de João da Serra com referência em 30/09/2026” e use **Baixar resumo em PDF**.
4. Na **Triagem**, abra `PED-2026-009` e consulte a análise no chat. Use **Ver mensagem original** para conferir o texto que originou o cartão.
5. Na **Triagem**, selecione **Urgente** no filtro **Urgência** e feche o menu de filtros. Abra `PED-2026-015` e confira no chat o pedido de retorno até `31/10/2026`, dia seguinte ao recebimento. Volte à fila, selecione **Normal** e feche o menu. Abra `PED-2026-014` e confira no chat o prazo de `11/11/2026` para disponibilizar os documentos no primeiro dia da inspeção. Selecione **Todas** para voltar à fila completa.
6. Em **Cadastros**, abra um produtor, produto ou documento para consultar e editar seus dados. O detalhe mostra os vínculos que impedem a exclusão. Use **Documento importado sem vínculo** para demonstrar uma exclusão.

O protótipo guarda os dados da demonstração no `localStorage`. Ao abrir uma fila salva de uma versão anterior, os cartões usam os rótulos atuais, as conversas permanecem disponíveis e os exemplos `PED-2026-014` e `PED-2026-015` aparecem uma vez cada. Use uma janela privativa para executar o roteiro do início. Para reiniciar a demonstração no navegador atual, remova a chave `sabor-da-terra-prototype-v1` nas ferramentas de desenvolvimento.
