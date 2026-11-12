# User stories

O usuário é o funcionário da cooperativa. As referências RF, RN e RNF apontam para [Requisitos](requisitos.md).

## US01 - Acessar a plataforma

Como funcionário, quero me autenticar para consultar informações e trabalhar nas solicitações da cooperativa.

Requisitos: RF16, RNF05.

Critérios de aceitação:

- Credenciais válidas permitem acessar as funções internas.
- Sem autenticação, consultas e alterações internas são rejeitadas.

## US02 - Revisar uma solicitação

Como funcionário, quero receber uma análise da mensagem para entender a demanda e suas pendências antes de decidir.

Requisitos: RF02, RF03, RF04, RF11, RF12; RN06 a RN08, RN16; RNF03, RNF06.

Critérios de aceitação:

- As 15 mensagens importadas aparecem na caixa de entrada da triagem com a indicação de que são da amostra. Repetir a carga mantém um único registro por mensagem.
- Mensagens novas de canais integrados aparecem na mesma caixa de entrada e passam pelo mesmo fluxo de triagem.
- A aplicação preserva o identificador de origem, o texto original, o remetente, o canal e a data de recebimento das mensagens. Uma nova entrega da mesma mensagem pelo canal integrado mantém um único registro.
- Dois pedidos independentes do mesmo contato na mesma conversa do canal geram solicitações separadas. Uma resposta com vínculo inequívoco a uma solicitação aberta fica registrada nela e atualiza apenas sua análise e suas pendências. Se o vínculo não puder ser identificado ou a solicitação estiver encerrada, a resposta inicia uma nova triagem.
- O cartão apresenta o resumo, o tipo, a urgência justificada e as pendências. Sua expansão abre a conversa iniciada pela análise do agente e permite conferir o texto original das mensagens recebidas, quando houver.
- A análise organiza os dados extraídos e preserva condições como "se tiver", a frequência de fornecimento e intenções adicionais, como uma oferta acompanhada de solicitação de cadastro.
- O assistente interpreta a mensagem PED-2026-011 em inglês e apresenta a triagem em português.
- Ao consultar o PED-2026-003 em novembro, o cartão mantém 29/10 como data de entrega solicitada e indica que o prazo venceu.

## US03 - Esclarecer ambiguidades

Como funcionário, quero discutir os pontos incertos com o assistente para completar a análise sem adivinhar a intenção do remetente.

Requisitos: RF01, RF07, RF10, RF13; RN03, RN06.

Critérios de aceitação:

- Produto indefinido, quantidade agregada ou data conflitante gera uma pergunta específica, preservando as informações já compreendidas.
- Quando o remetente usa uma expressão como "amanhã", o assistente calcula a data a partir do recebimento daquela mensagem. Retomar a conversa em outro dia não altera a interpretação.
- O assistente registra o esclarecimento na conversa e atualiza a análise, a sugestão e os alertas afetados, preservando a mensagem original.
- Perguntas de acompanhamento usam o contexto daquela conversa, sem incorporar dados de outra solicitação.

## US04 - Avaliar uma sugestão de atendimento

Como funcionário, quero conhecer os produtores candidatos para comparar alternativas de atendimento.

Requisitos: RF14, RF23; RN01 a RN04, RN10, RN13.

Critérios de aceitação:

- A sugestão identifica candidatos, fontes, quantidades justificáveis e disponibilidade ainda não confirmada. Para pedidos cadastrados, considera o saldo a alocar de cada item.
- Produtores inaptos são excluídos da sugestão para aquele atendimento, com indicação do motivo. Dados ausentes ou conflitantes aparecem como pendências.
- O funcionário pode discutir alternativas no chat e registra as alocações escolhidas na gestão do pedido.

## US05 - Acompanhar a triagem

Como funcionário, quero consultar a situação das solicitações para identificar o que ainda depende de decisão.

Requisitos: RF12, RF15; RN10.

Critérios de aceitação:

- A solicitação apresenta um dos estados definidos no RF15 e as pendências existentes.
- Sem fornecedor apto, a análise explica o motivo. O funcionário pode buscar esclarecimentos ou encerrar sem atendimento.
- O encerramento registra o resultado da triagem e as pendências restantes.

## US06 - Consultar documentos e dados

Como funcionário, quero fazer perguntas sobre os registros da cooperativa para responder às demandas com fontes verificáveis.

Requisitos: RF01, RF05, RF06, RF07, RF17; RN01, RN03, RN05, RN06; RNF06.

Critérios de aceitação:

- A consulta pode combinar documentos e dados operacionais na mesma conversa.
- Em uma consulta iniciada no chat sem data informada, o assistente usa a data da consulta e a indica na resposta.
- A resposta identifica documentos e registros ou trechos que sustentam as afirmações. Consultas sobre certificação verificam validade e produto coberto; consultas sobre lote identificam sua origem registrada.
- A consulta ao LOT-2026-0094 informa 300 unidades de alface. No LOT-2026-0099, o assistente indica que "40 maços (kg)" tem unidade ambígua e deixa a quantidade fora dos totais.
- Preços informam vigência e condições. Informação ausente ou conflitante é explicitada, sem completar a resposta por suposição.
- A citação permite ler o documento completo na plataforma e baixar o arquivo original usado na resposta, mesmo após a substituição no cadastro.

## US07 - Consultar e baixar o resumo de um produtor

Como funcionário, quero gerar e baixar em PDF um resumo por produtor para informar suas vendas, pedidos alocados e pendências financeiras.

Requisitos: RF08, RF18, RF23; RN03, RN09; RNF04.

Critérios de aceitação:

- O resumo identifica produtor, período e data de referência, com fontes dos valores e registros apresentados.
- O resumo usa a data da transação para selecionar vendas e a data de pagamento para selecionar pagamentos registrados. No PED-2026-012, os R$ 940 de vendas ao Mercado Bom Preço entram em setembro e o pagamento registrado entra em outubro. Quantidades respeitam produto e unidade.
- O resumo distingue pendências vencidas e a vencer na data de referência, inclusive as de períodos anteriores. Quando não encontra registros, o assistente informa a ausência. O pagamento registrado, por si só, não comprova repasse bancário.
- O resumo lista as alocações cadastradas para o produtor conforme a previsão de fornecimento no período. Após o cancelamento do pedido, as alocações removidas deixam de aparecer nos novos resumos.
- O resumo é acompanhado da opção "Baixar resumo em PDF". O arquivo preserva o conteúdo e as fontes exibidos.

## US08 - Preparar e enviar uma notificação

Como funcionário, quero preparar e enviar uma notificação para comunicar uma demanda ao produtor.

Requisitos: RF09, RF24; RN11, RN14, RN17.

Critérios de aceitação:

- O rascunho identifica o produtor, os produtos, as quantidades e os prazos conhecidos e indica o que ainda precisa de confirmação.
- Uma consulta de disponibilidade é distinta de uma comunicação de alocação confirmada nos registros consultados.
- A notificação só comunica uma alocação futura como confirmada se os dados atuais comprovarem a aptidão do produtor. Se faltar comprovação obrigatória, a aplicação sinaliza a pendência para revisão.
- O funcionário pode editar ou copiar o texto, escolher um canal integrado e conferir o contato do produtor antes de autorizar o envio.
- Na demonstração, o envio fica disponível apenas para destinos de teste que a equipe vinculou ao produtor. Se faltar destino válido ou o canal impedir o envio, a aplicação informa o motivo e oferece a opção de copiar o rascunho.
- A aplicação só envia a versão revisada após a confirmação explícita do funcionário. O histórico registra o texto autorizado, o destinatário, o canal, o funcionário e o resultado do envio.
- Se o pedido for cancelado entre a abertura do rascunho e a confirmação, a aplicação bloqueia o envio da notificação de alocação e informa o motivo.

## US09 - Retomar o trabalho

Como funcionário, quero reencontrar as solicitações e suas conversas para continuar a triagem após sair da aplicação.

Requisitos: RF10; RNF01.

Critérios de aceitação:

- Após reabrir a aplicação e se autenticar, o funcionário encontra mensagens, histórico de envios, análises, conversas, cadastros, pedidos, agendamentos e alocações.
- Ao retomar uma conversa, o assistente considera seus esclarecimentos anteriores e mantém o contexto separado das demais solicitações.

## US10 - Recuperar uma operação com falha

Como funcionário, quero saber quando uma operação falhou e poder tentar novamente para continuar o atendimento.

Requisitos: RN18; RNF02, RNF03.

Critérios de aceitação:

- A interface indica processamento e informa falhas. Após 60 segundos sem conclusão, informa a demora e oferece nova tentativa. Para envios, aplica a RN18.
- A solicitação permanece disponível. Repetir a mesma operação mantém um único registro, inclusive na confirmação de pedidos e agendamentos pelo chat, na geração de ocorrências e no cadastro de alocações. Uma alteração rejeitada mantém o registro anterior.
- O resultado atrasado de uma tentativa anterior não substitui análises ou esclarecimentos mais recentes.
- A mesma confirmação aciona uma única tentativa de envio. Em caso de falha confirmada, a mensagem fica disponível para nova tentativa pelo funcionário. Se o resultado for incerto, a aplicação indica a necessidade de conferir o envio antes de permitir nova tentativa.

## US11 - Manter os cadastros

Como funcionário, quero manter os cadastros de produtores, produtos e documentos para trabalhar com dados atualizados.

Requisitos: RF19; RNF06.

Critérios de aceitação:

- O funcionário pode criar, consultar e editar produtores, produtos e documentos. Pode excluir registros sem vínculos.
- A aplicação bloqueia a exclusão de registros vinculados a pedidos, alocações, agendamentos, lotes, transações financeiras ou citações e informa o vínculo que impede a exclusão.
- As consultas e sugestões do assistente usam os cadastros atualizados após essas operações.
- Após editar um produtor da base e excluir um documento importado sem vínculos, uma nova carga na mesma base preserva a edição e a exclusão.

## US12 - Gerenciar pedidos

Como funcionário, quero gerenciar os pedidos da cooperativa para acompanhar as demandas cadastradas.

Requisitos: RF20; RN14.

Critérios de aceitação:

- O funcionário pode criar, consultar, editar e cancelar pedidos.
- No cadastro manual ou na edição, o funcionário registra as condições que valem para todo o pedido e as que se aplicam a itens específicos.
- Quando houver uma solicitação de origem, o pedido mantém o vínculo com ela.
- A aplicação registra o cancelamento e exclui as alocações do pedido na mesma operação. O pedido continua consultável com o estado cancelado.

## US13 - Cadastrar um pedido pelo chat

Como funcionário, quero revisar e confirmar um pedido no chat para registrá-lo na gestão de pedidos.

Requisitos: RF20, RF21; RN16; RNF03.

Critérios de aceitação:

- O assistente apresenta no chat o comprador, os itens, as quantidades, as unidades, o prazo e as condições de atendimento. Na revisão, o funcionário ajusta os dados e decide se inclui itens condicionais.
- Se o comprador corrigir a quantidade de 30 para 15 enquanto o rascunho estiver aberto, o funcionário vê a correção antes de confirmar a versão que deseja cadastrar.
- A confirmação explícita do funcionário cadastra a versão revisada. O pedido fica disponível para consulta e edição no CRUD.
- Ao consultar o pedido cadastrado a partir do PED-2026-004, o funcionário encontra a exigência de certificação orgânica no item de mel.

## US14 - Agendar pedidos

Como funcionário, quero agendar pedidos para que cada ocorrência entre na triagem com a antecedência definida.

Requisitos: RF22; RN15; RNF03.

Critérios de aceitação:

- O funcionário pode criar, consultar, editar e cancelar agendamentos semanais. O agendamento registra o comprador, os itens, as quantidades, as unidades, as condições de atendimento e a primeira data de fornecimento. O funcionário informa a antecedência da triagem em dias corridos.
- Pelo chat, o assistente prepara o rascunho do agendamento para revisão e ajustes. A confirmação explícita do funcionário cadastra a versão revisada.
- Na data programada para a triagem, cada ocorrência gera uma única solicitação vinculada ao agendamento. A solicitação traz o comprador, os itens, as quantidades, as unidades, as condições e a data de fornecimento. Um fornecimento de terça-feira com dois dias de antecedência entra na triagem no domingo.
- Na retomada do serviço ou ao salvar um agendamento novo ou editado, a aplicação gera de imediato as solicitações das ocorrências pendentes com triagem atrasada e fornecimento para hoje ou depois. Se o fornecimento já passou, registra a ocorrência como perdida e segue com a próxima.
- Um agendamento salvo na segunda-feira para fornecimento na terça-feira, com dois dias de antecedência, gera a primeira solicitação na segunda-feira, uma única vez.
- Alterar ou cancelar um agendamento afeta apenas ocorrências pendentes.

## US15 - Gerenciar alocações

Como funcionário, quero gerenciar as alocações de cada item do pedido para registrar quem atenderá a demanda.

Requisitos: RF20, RF23; RN01, RN02, RN12 a RN14.

Critérios de aceitação:

- O funcionário pode cadastrar, consultar, editar e excluir alocações. Cada alocação identifica o item do pedido, o produtor, a quantidade e a unidade.
- O cadastro e a edição exigem produtor apto e disponibilidade confirmada pelo funcionário.
- A quantidade alocada é positiva e usa unidade compatível. A soma das alocações respeita o limite solicitado para o item.
- A aplicação usa os mesmos critérios de aptidão da triagem. A alocação exige comprovação das restrições sanitárias, contratuais e documentais aplicáveis, mesmo quando elas não constam do pedido. No PED-2026-004, a aplicação bloqueia a alocação e informa a pendência se houver número de DAP/CAF sem prova de vigência.
- O funcionário precisa ajustar ou excluir as alocações afetadas antes de salvar uma alteração do pedido que entre em conflito com elas.

## US16 - Responder ao remetente

Como funcionário, quero revisar uma resposta para esclarecer a solicitação ou informar o resultado da triagem ao remetente.

Requisitos: RF24; RN17.

Critérios de aceitação:

- A pedido do funcionário, o assistente prepara um rascunho. O funcionário pode editar e copiar o texto, inclusive nas mensagens da amostra.
- Se o remetente pedir documentos ou dados pessoais ou bancários, o assistente avisa o funcionário. No PED-2026-009, o aviso lista os documentos e dados cadastrais solicitados. O rascunho omite esse material até o funcionário decidir o que compartilhar.
- A opção de envio só fica disponível para mensagens novas de canais integrados quando há um destino válido e o canal permite o envio. O funcionário confere o destinatário e o canal, e a aplicação envia o texto revisado pelo canal de origem após a confirmação explícita.
- Quando o canal de origem não está integrado, falta um destino válido ou o canal impede o envio, a aplicação informa o motivo e oferece a opção de copiar a resposta.
- O histórico registra o texto autorizado, o destinatário, o canal, o funcionário e o resultado do envio.
