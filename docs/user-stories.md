# User stories

O usuário é o funcionário da cooperativa. As referências RF e RNF apontam para [Requisitos](requisitos.md).

## US01 - Acessar a plataforma

Como funcionário, quero me autenticar para consultar informações e trabalhar nas solicitações da cooperativa.

Requisitos: RF16, RNF05.

Critérios de aceitação:

- Credenciais válidas permitem acessar as funções internas.
- Sem autenticação, consultas e alterações internas são rejeitadas.

## US02 - Revisar uma solicitação

Como funcionário, quero receber uma análise da mensagem para entender a demanda e suas pendências antes de decidir.

Requisitos: RF02, RF03, RF04, RF11, RF12, RF15, RF25; RNF03, RNF06, RNF07.

Critérios de aceitação:

- As 15 mensagens enviadas pelo script de apresentação entram na mesma fila e passam pelo mesmo fluxo de triagem que as mensagens dos canais integrados. Reexecutar o script mantém um único registro por mensagem.
- O sistema preserva o texto original, o remetente, o canal e a data de recebimento de cada mensagem, além do identificador de origem quando disponível. Uma nova entrega da mesma mensagem pelo canal integrado mantém um único registro.
- O sistema, ao receber um novo pedido como resposta direta a uma mensagem de outra solicitação ainda não finalizada do mesmo contato, cria uma solicitação separada e preserva a anterior.
- O sistema registra na conversa da solicitação ainda não finalizada a resposta que dá continuidade à demanda e tem vínculo inequívoco. Atualiza a análise, as pendências e os dados do cartão afetados pela resposta. A análise inicial e o estado do atendimento são preservados. O sistema abre nova triagem quando o vínculo é incerto ou a solicitação anterior está finalizada.
- O sistema, se o Telegram estiver integrado, registra separadamente duas mensagens com o mesmo `message_id` em chats diferentes do mesmo bot. O sistema, ao receber uma reentrega de uma delas, reaproveita apenas o registro do chat correspondente.
- O cartão apresenta o resumo, o tipo, a urgência e o estado atual do atendimento.
- O funcionário pode abrir o chat pelo cartão para consultar a análise inicial, o motivo da urgência e as pendências identificadas. Ao voltar à conversa, pode consultar o histórico. Se a solicitação tiver mensagens recebidas, pode consultar o texto original de cada uma.
- A análise organiza os dados extraídos e preserva condições como "se tiver", a frequência de fornecimento e intenções adicionais, como uma oferta acompanhada de solicitação de cadastro.
- O assistente interpreta a mensagem PED-2026-011 em inglês e apresenta a triagem em português.
- Ao abrir o chat do PED-2026-003 em novembro, o funcionário pode consultar 29/10 como a data de entrega interpretada na triagem.

## US03 - Esclarecer ambiguidades

Como funcionário, quero discutir os pontos incertos com o assistente para completar a análise sem adivinhar a intenção do remetente.

Requisitos: RF01, RF07, RF10, RF13.

Critérios de aceitação:

- Produto indefinido, quantidade agregada ou data conflitante gera uma pergunta específica, preservando as informações já compreendidas.
- Quando o remetente usa uma expressão como "amanhã", o assistente calcula a data a partir do recebimento daquela mensagem. Retomar a conversa em outro dia não altera a interpretação.
- O assistente registra o esclarecimento na conversa e atualiza a análise, a sugestão e os alertas afetados, preservando a mensagem original.
- Perguntas de acompanhamento usam o contexto daquela conversa, sem incorporar dados de outra solicitação.

## US04 - Avaliar uma sugestão de atendimento

Como funcionário, quero conhecer os produtores candidatos para comparar alternativas de atendimento.

Requisitos: RF03, RF06, RF14, RF22, RF26, RF27, RF30, RF31, RF42.

Critérios de aceitação:

- A sugestão identifica os produtores candidatos e cita as fontes usadas.
- O assistente indica o que o funcionário ainda precisa confirmar sobre a disponibilidade dos produtores sugeridos.
- Para um pedido cadastrado, o assistente usa na sugestão o saldo de cada item obtido pelas ferramentas da aplicação.
- O saldo corresponde à quantidade solicitada menos o total das alocações operacionais vigentes do item no momento da consulta. O cálculo usa a unidade do item e converte quantidades apenas quando houver equivalência conhecida.
- O assistente exclui produtores inaptos da sugestão e indica o motivo. O assistente apresenta dados ausentes ou conflitantes como pendências e indica a aptidão sem comprovação como pendente, separada dos candidatos aptos.
- Na triagem do PED-2026-004, se a base só informar o número do DAP ou CAF, o assistente aponta que falta comprovar a vigência e cita o contrato do PNAE.
- O funcionário pode discutir alternativas no chat e registrar as alocações escolhidas na gestão do pedido ou revisar e confirmar um rascunho de alocação no chat.

## US05 - Acompanhar a triagem

Como funcionário, quero consultar a situação das solicitações para identificar o que ainda depende de decisão.

Requisitos: RF12, RF15, RF25.

Critérios de aceitação:

- Na fila de triagem, o funcionário vê o estado atual de cada solicitação. As pendências ficam disponíveis no chat da solicitação.
- Uma solicitação nova aparece como `recebida`. Quando o funcionário abre o cartão pela primeira vez, o sistema muda o estado para `em análise`.
- Sem fornecedor apto, a análise explica o motivo. O funcionário pode buscar esclarecimentos ou encerrar sem atendimento.
- Quando o funcionário encerra o atendimento, o sistema muda o estado da solicitação para `finalizada`.

## US06 - Consultar documentos e dados

Como funcionário, quero fazer perguntas sobre os registros da cooperativa para responder às demandas com fontes verificáveis.

Requisitos: RF01, RF05, RF06, RF07, RF17, RF41; RNF06.

Critérios de aceitação:

- A consulta pode combinar documentos e dados operacionais na mesma conversa.
- Em uma consulta iniciada no chat sem data informada, o assistente usa a data da consulta e a indica na resposta.
- A resposta identifica documentos e registros ou trechos que sustentam as afirmações. Consultas sobre certificação verificam validade e produto coberto; consultas sobre lote identificam sua origem registrada.
- Após a carga de `lotes.csv`, os 20 Lotes ficam disponíveis para consulta com seus identificadores originais e os dados fornecidos de produtor, produto, comprador, pedido histórico, quantidade, unidade identificada, datas, temperatura de transporte, inspeção visual e observações.
- A consulta ao LOT-2026-0094 informa que P004 forneceu 300 unidades de alface, com colheita em 06/09/2026 e entrega em 08/09/2026, para o pedido histórico PED-2026-SEP-008. A resposta identifica `lotes.csv` e o lote como fonte.
- A referência PED-2026-SEP-008 permanece disponível quando o pedido original estiver ausente da base. A quantidade originalmente solicitada e o prazo combinado são apresentados como desconhecidos quando faltarem registros que os comprovem.
- No LOT-2026-0099, o assistente preserva a descrição "40 maços (kg)", indica a unidade ambígua e deixa a quantidade fora de somas e conversões até esclarecimento.
- Preços informam vigência e condições. Informação ausente ou conflitante é explicitada, sem completar a resposta por suposição.
- A citação permite ler o documento completo na plataforma e baixar o arquivo original usado na resposta.

## US07 - Consultar e baixar o resumo de um produtor

Como funcionário, quero gerar e baixar em PDF um resumo por produtor para informar suas vendas, fornecimentos realizados, pedidos alocados e pendências financeiras.

Requisitos: RF08, RF18, RF22, RF41; RNF04, RNF06.

Critérios de aceitação:

- O resumo identifica produtor, período e data de referência, com fontes dos valores e registros apresentados.
- O assistente combina os registros financeiros, os Lotes e as alocações operacionais do produtor conforme os critérios de período e data de referência do RF08. O resumo apresenta os resultados dos cálculos obtidos pelas ferramentas da aplicação e suas fontes.
- Os cálculos financeiros são conferidos com valores esperados a partir dos registros selecionados. Os valores apresentados pelo assistente correspondem aos resultados desses cálculos.
- O resumo usa a data da transação para selecionar vendas e a data de pagamento para selecionar pagamentos registrados. No PED-2026-012, os R$ 940 de vendas ao Mercado Bom Preço entram em setembro e o pagamento registrado entra em outubro. Quantidades respeitam produto e unidade.
- O resumo distingue pendências vencidas e a vencer na data de referência, inclusive as de períodos anteriores. Quando não encontra registros, o assistente informa a ausência. O pagamento registrado, por si só, não comprova repasse bancário.
- No resumo da produtora P001 com referência em 30/09/2026, os R$ 940 do Mercado Bom Preço aparecem como valor a vencer. O vencimento é em 02/10/2026 e o pagamento consta em 01/10/2026.
- O resumo lista as alocações operacionais do produtor com entrega prevista no período, inclusive quando só parte do intervalo de entrega cai no período, e os Lotes pela data efetiva de entrega. Identifica os fornecimentos realizados e previstos, suas datas e seus totais por produto e unidade. Quantidades ambíguas aparecem como pendências e ficam fora dos totais até esclarecimento.
- O assistente pede esclarecimento sobre quantidades agregadas ou ambíguas antes de incluí-las nos totais. As conversões de quantidades usadas no resumo dependem de equivalência conhecida.
- O resumo de P004 para setembro de 2026 apresenta 300 unidades de alface e 150 maços de coentro entregues em 08/09/2026, citando LOT-2026-0094 e LOT-2026-0095 de `lotes.csv`.
- Para P004, o período de 08/09/2026 a 08/09/2026 inclui esses dois Lotes. O período de 06/09/2026 a 06/09/2026 informa ausência de entregas registradas, usando a data efetiva de entrega para selecionar o histórico.
- Repetir a carga da mesma base mantém os 20 Lotes, seus identificadores e fontes, com uma ocorrência de cada Lote e as mesmas quantidades nos resumos.
- Após o cancelamento de um pedido, as alocações operacionais removidas deixam de aparecer nos novos resumos. Os Lotes históricos continuam disponíveis nos resumos dos respectivos períodos.
- O resumo é acompanhado da opção "Baixar resumo em PDF". O arquivo preserva o conteúdo e as fontes exibidos.

## US08 - Preparar e enviar uma notificação

Como funcionário, quero preparar e enviar uma notificação para comunicar uma demanda ao produtor.

Requisitos: RF09, RF19, RF34 a RF36, RF40, RF44, RF45.

Critérios de aceitação:

- O rascunho identifica o produtor, os produtos, as quantidades e os prazos conhecidos e indica o que ainda precisa de confirmação.
- O sistema permite enviar uma consulta de disponibilidade sem alocação confirmada, respeitando as condições de envio do RF40. Se o texto revisado confirmar um compromisso de fornecimento, o sistema aplica o RF44 na confirmação e antes de cada tentativa.
- A notificação só comunica uma alocação futura como confirmada se os dados atuais comprovarem a aptidão do produtor. Se faltar comprovação obrigatória, a aplicação sinaliza a pendência para revisão.
- O funcionário pode editar e copiar o texto e escolher um canal integrado.
- O sistema mostra o destinatário e o canal da notificação para o funcionário conferir antes de confirmar.
- Na demonstração, o envio fica disponível apenas para destinos de teste que a equipe vinculou ao produtor. Se faltar destino válido ou o canal impedir o envio, a aplicação informa o motivo e oferece a cópia do rascunho conforme o RF34.
- O sistema só envia a versão revisada após a confirmação explícita do funcionário.
- O assistente deixa dados pessoais ou bancários das fontes fora do texto da notificação e da versão copiável até o funcionário autorizar os dados específicos para aquele destinatário.
- O sistema registra em uma mensagem no chat o texto autorizado, o funcionário que confirmou, o destinatário, o canal e o resultado do envio.
- O sistema bloqueia o envio da notificação de compromisso e informa o motivo se o pedido for cancelado antes da confirmação ou entre a confirmação e o disparo.
- Se, após uma falha, as alocações deixarem de cobrir a quantidade prometida, o sistema bloqueia o reenvio do rascunho e informa o motivo.

## US09 - Retomar o trabalho

Como funcionário, quero reencontrar as solicitações e suas conversas para continuar a triagem após sair da aplicação.

Requisitos: RF10, RF36; RNF01.

Critérios de aceitação:

- Após reabrir a aplicação e se autenticar, o funcionário encontra mensagens, análises, conversas, documentos adicionados, pedidos, agendamentos, alocações e Lotes. O histórico de envios fica disponível no chat.
- Ao retomar uma conversa, o assistente considera seus esclarecimentos anteriores e mantém o contexto separado das demais solicitações.

## US10 - Recuperar uma operação com falha

Como funcionário, quero saber quando uma operação falhou e poder tentar novamente para continuar o atendimento.

Requisitos: RF36, RF40, RF44, RF45; RNF02, RNF03, RNF08 a RNF11.

Critérios de aceitação:

- A interface indica processamento e informa falhas. Após 60 segundos sem conclusão, informa a demora.
- Nas operações de envio, o sistema só oferece nova tentativa após falha confirmada e exige nova confirmação explícita do funcionário conforme o RF45. Nas demais operações, oferece nova tentativa após o aviso de demora.
- Se a triagem falhar antes de criar o cartão, o funcionário pode tentar novamente a partir da entrada registrada. Se a solicitação já tiver sido criada, ela permanece disponível.
- Falhas do modelo e das consultas são informadas na interface e preservam a solicitação ou a entrada registrada para nova tentativa, conforme o RNF11.
- Repetir a mesma operação mantém um único registro, inclusive na confirmação de pedidos e agendamentos pelo chat, na geração de ocorrências e no cadastro de alocações.
- Uma alteração rejeitada mantém o registro anterior.
- O resultado atrasado de uma tentativa anterior não substitui análises ou esclarecimentos mais recentes.
- O sistema aciona no máximo uma tentativa ao receber a mesma confirmação mais de uma vez ou duas confirmações simultâneas da mesma versão do rascunho para o mesmo destinatário e canal. O sistema, após um envio bem-sucedido, bloqueia nova tentativa dessa versão para o mesmo destinatário e canal.
- O sistema mantém o reenvio bloqueado durante a tentativa. Se a tentativa terminar sem confirmação do resultado, a mensagem de envio no chat mostra "Resultado incerto" e explica que reenviar pode duplicar a mensagem. O reenvio fica bloqueado mesmo se o funcionário editar o rascunho. Se o canal confirmar o resultado mais tarde, o sistema atualiza a mensagem no chat.
- O sistema libera uma nova tentativa após confirmar a falha anterior e receber nova confirmação explícita do funcionário.

## US11 - Gerenciar documentos

Como funcionário, quero gerenciar os documentos da base para que o assistente possa consultá-los e citá-los nas respostas.

Requisitos: RF28, RF29, RF38; RNF01, RNF05, RNF06.

Critérios de aceitação:

- O funcionário pode adicionar um documento, encontrá-lo na lista, abrir seu conteúdo e baixar o arquivo com o nome original.
- O sistema só exibe o documento na lista depois de gravar o arquivo e salvar o registro.
- O funcionário pode adicionar dois documentos com o mesmo nome. Em cada registro, pode abrir e baixar o arquivo correspondente.
- O funcionário pode excluir um documento sem citações. O sistema remove o arquivo e retira o documento da lista.
- O sistema bloqueia a exclusão de um documento citado, preserva o registro e o arquivo e informa ao funcionário qual citação impede a operação.
- O assistente pode consultar e citar o documento adicionado após o processamento.
- O sistema preserva as exclusões de documentos importados ao repetir a carga da mesma base.

## US12 - Gerenciar pedidos

Como funcionário, quero gerenciar os pedidos da cooperativa para acompanhar as demandas cadastradas.

Requisitos: RF19, RF39.

Critérios de aceitação:

- O funcionário pode criar, consultar, editar e cancelar pedidos.
- No cadastro manual e na edição, o funcionário pode informar uma data ou um intervalo de entrega. O pedido salvo mostra o prazo informado.
- No cadastro manual e na edição, o funcionário pode informar as condições de atendimento. Ao consultar o pedido salvo, ele vê o texto que confirmou.
- A aplicação registra o cancelamento e exclui as alocações operacionais do pedido na mesma operação. O pedido continua consultável com o estado cancelado e os Lotes históricos são preservados.

## US13 - Cadastrar um pedido pelo chat

Como funcionário, quero revisar e confirmar um pedido no chat para registrá-lo na gestão de pedidos.

Requisitos: RF19, RF20, RF30 a RF32, RF39; RNF03.

Critérios de aceitação:

- O assistente apresenta no chat um rascunho com o comprador, os itens, as quantidades, as unidades, o prazo e as condições de atendimento.
- Se o comprador pedir entrega de 4 a 8 de novembro, o rascunho mostra o intervalo e o sistema o salva ao confirmar o pedido. Se o funcionário escolher um dia específico na revisão, o sistema salva a data escolhida.
- Ao revisar o rascunho no chat, o funcionário pode ajustar os dados e decidir se inclui os itens solicitados sob condição.
- Se uma resposta do comprador vinculada à solicitação corrigir a quantidade de 30 para 15 enquanto o rascunho estiver aberto, o funcionário vê a correção antes de confirmar a versão que deseja cadastrar.
- Após a confirmação explícita do funcionário, o sistema cadastra a versão revisada. O pedido fica disponível para consulta e edição na gestão de pedidos.
- Quando o pedido é cadastrado pela triagem, o funcionário pode abri-lo pelo chat da solicitação de origem, inclusive depois de reabrir a conversa.
- Ao consultar o pedido cadastrado a partir do PED-2026-004, o funcionário encontra a exigência de certificação orgânica para o mel no texto salvo das condições.

## US14 - Agendar pedidos

Como funcionário, quero agendar pedidos para que cada ocorrência entre na triagem com a antecedência definida.

Requisitos: RF21, RF24, RF30, RF31, RF33, RF43; RNF03.

Critérios de aceitação:

- O funcionário pode cadastrar, consultar, editar e cancelar agendamentos semanais.
- O sistema registra o comprador, os itens, as quantidades, as unidades, as condições de atendimento confirmadas, a primeira data de fornecimento e a antecedência da triagem em dias corridos ao salvar um agendamento.
- O assistente prepara o rascunho do agendamento no chat. O funcionário pode revisar e ajustar os dados antes de confirmar.
- O sistema cadastra a versão revisada do agendamento após a confirmação explícita do funcionário no chat.
- Na data programada para a triagem, cada ocorrência gera uma única solicitação vinculada ao agendamento. Um fornecimento de terça-feira com dois dias de antecedência entra na triagem no domingo.
- A solicitação gerada preserva o comprador, os itens, as quantidades, as unidades, as condições de atendimento e a data de fornecimento daquela ocorrência.
- O sistema, ao retomar o serviço ou salvar um agendamento novo ou editado, gera de imediato as solicitações das ocorrências pendentes com triagem prevista para hoje ou antes e fornecimento para hoje ou depois.
- O sistema registra como perdida a ocorrência pendente cuja data de fornecimento já passou e segue para a próxima.
- A recuperação das ocorrências pendentes mantém uma única solicitação por ocorrência.
- Um agendamento salvo na segunda-feira para fornecimento na terça-feira, com dois dias de antecedência, gera a primeira solicitação na segunda-feira, uma única vez.
- O sistema, ao salvar um agendamento de fornecimento para hoje com antecedência zero depois da rotina do dia, gera a primeira solicitação de imediato, uma única vez. O sistema faz o mesmo ao retomar o serviço quando essa ocorrência ainda estiver pendente.
- Alterar ou cancelar um agendamento afeta apenas ocorrências pendentes.
- Se a entrega de terça-feira já entrou na triagem e o funcionário muda o dia da série para quinta-feira da mesma semana, a solicitação de terça mantém os dados originais. A primeira entrega de quinta-feira fica para a semana seguinte, mesmo que a solicitação de terça tenha sido gerada no domingo anterior.

## US15 - Gerenciar alocações

Como funcionário, quero gerenciar as alocações operacionais de cada item do pedido para registrar quem atenderá a demanda.

Requisitos: RF19, RF22.

Critérios de aceitação:

- O funcionário pode cadastrar, consultar, editar e excluir alocações operacionais. Cada alocação identifica o item do pedido, o produtor, a quantidade e a unidade.
- O sistema exige pedido ativo e disponibilidade confirmada pelo funcionário para cadastrar ou editar uma alocação.
- A quantidade alocada é positiva. O sistema converte as quantidades para a unidade do item antes de verificar se a soma respeita o limite solicitado. Se a unidade for incompatível ou o total ultrapassar o limite, o sistema rejeita o salvamento.
- Se o funcionário tentar cadastrar ou editar uma alocação para o produtor P015, marcado como inativo na base, o sistema impede o salvamento e informa o motivo.
- O funcionário precisa ajustar ou excluir as alocações operacionais afetadas antes de salvar uma alteração do pedido que entre em conflito com elas.
- O sistema rejeita o salvamento de uma alocação após o cancelamento do pedido, mesmo se o formulário tiver sido aberto antes. O sistema mantém o pedido cancelado sem alocações operacionais mesmo se o salvamento e o cancelamento forem simultâneos e preserva os Lotes históricos.

## US16 - Responder ao remetente

Como funcionário, quero revisar uma resposta para esclarecer a solicitação ou informar o resultado da triagem ao remetente.

Requisitos: RF23, RF34 a RF37, RF40, RF44, RF45.

Critérios de aceitação:

- O assistente, a pedido do funcionário, prepara um rascunho de resposta. O funcionário pode editar e copiar o texto. Para as mensagens enviadas pelo script da apresentação, a aplicação oferece apenas revisão e cópia da resposta.
- O assistente, quando o remetente pede documentos, dados pessoais ou dados bancários, avisa o funcionário. O assistente lista, no aviso do PED-2026-009, os documentos e dados cadastrais solicitados.
- O assistente, ao responder a uma nova consulta integrada sobre a validade de uma certificação cuja fonte contém CPF, informa a validade e deixa o CPF fora do rascunho e da versão copiável. O assistente inclui somente os dados específicos que o funcionário autorizar para aquele destinatário.
- O sistema bloqueia a cópia e o envio se o funcionário incluir um CPF ao editar o rascunho e ainda não tiver autorizado o compartilhamento desse dado com o destinatário. O sistema libera a cópia após essa autorização e aplica as condições de envio do RF40.
- O sistema só oferece o envio de respostas a mensagens recebidas pela integração quando há um destino válido e o canal permite o envio.
- O sistema mostra o destinatário e o canal para o funcionário conferir antes de confirmar. O sistema envia o texto revisado pelo canal de origem após a confirmação explícita do funcionário.
- O sistema bloqueia, antes do disparo, uma resposta que confirma ao comprador o fornecimento de 30 unidades quando as alocações vigentes cobrem apenas 20. O sistema informa o motivo do bloqueio.
- Quando o canal de origem não está integrado, falta um destino válido ou o canal impede o envio, a aplicação informa o motivo e oferece a cópia da resposta conforme o RF34.
- O sistema registra em uma mensagem no chat o texto autorizado, o funcionário que confirmou, o destinatário, o canal e o resultado do envio.

## US17 - Cadastrar uma alocação pelo chat

Como funcionário, quero revisar e confirmar uma alocação no chat para registrar quem atenderá um item do pedido.

Requisitos: RF22, RF27, RF30, RF31, RF42, RF46; RNF01, RNF03, RNF05.

Critérios de aceitação:

- O assistente apresenta no chat um rascunho com pedido cadastrado, item, produtor, quantidade e unidade, além da data ou do intervalo de entrega e da situação da confirmação de disponibilidade.
- Quando faltar informação ou houver ambiguidade no pedido, item, produtor, quantidade ou unidade, o assistente pede esclarecimento antes de oferecer o cadastro.
- O funcionário pode ajustar pedido, item, produtor, quantidade e unidade antes de confirmar. A confirmação de disponibilidade corresponde aos dados do fornecimento na versão revisada.
- O sistema cadastra a versão revisada após a confirmação explícita do funcionário e usa a mesma operação e as mesmas validações do cadastro direto de alocações.
- O sistema rejeita o cadastro e informa o motivo no chat quando o pedido estiver cancelado, o produtor estiver inativo, a disponibilidade estiver pendente, a quantidade for inválida, a unidade for incompatível ou o total ultrapassar a quantidade solicitada.
- Se outras alocações consumirem o saldo enquanto o rascunho estiver aberto, o sistema verifica o saldo atual na gravação e rejeita o cadastro que ultrapassar o limite. O sistema também rejeita o cadastro se o pedido tiver sido cancelado nesse intervalo.
- Após cadastrar a alocação, o sistema a apresenta no chat e permite abrir o pedido correspondente. O funcionário pode consultar e editar a alocação pela gestão do pedido.
- Repetir a mesma confirmação mantém uma única alocação cadastrada.
- Após reabrir a aplicação, o funcionário pode consultar a alocação salva. Ela aparece nos resumos do produtor conforme o período previsto de entrega.
- O sistema rejeita o cadastro sem autenticação válida.
