# Requisitos

## Escopo

O assistente é de uso interno da cooperativa fictícia Sabor da Terra. Ele analisa as solicitações que entram na triagem, responde a consultas sobre documentos e dados operacionais com indicação das fontes e prepara resumos e notificações para produtores a pedido dos funcionários. Os funcionários conduzem o atendimento a compradores, produtores e auditores e autorizam as respostas e notificações antes do envio pela aplicação.

A equipe consulta os dados e documentos da base fornecida pelo chat. A aplicação permite gerenciar pedidos e agendamentos semanais e registrar alocações de produtores por item do pedido.

A aplicação disponibiliza o histórico inicial de alocações a partir dos registros de fornecimento realizado presentes em `lotes.csv`. Cada registro é tratado como um Lote e mantém os dados e a fonte de origem.

No cenário do enunciado, a cooperativa recebe de 60 a 100 pedidos por dia por e-mail, formulário web e mensagens de texto. Para a demonstração, a aplicação integra e-mail e WhatsApp.

Os critérios de aceitação estão nas [histórias de usuário](user-stories.md).

## Requisitos funcionais

### RF01 - Conversar com o assistente

O funcionário deve poder conversar com o assistente por texto.

### RF02 - Interpretar pedidos em linguagem natural

O assistente deve interpretar pedidos escritos em linguagem coloquial, em português ou em inglês, com abreviações, erros de digitação, informações implícitas e ambiguidades. A triagem deve ser em português.

regras de negócio:

- O assistente deve interpretar datas relativas a partir da data de recebimento da mensagem em que aparecem.
- O assistente deve pedir esclarecimento quando a data explícita, o dia da semana ou outra referência de prazo entrarem em conflito.

### RF03 - Extrair dados dos pedidos

O assistente deve extrair e organizar produtos, quantidades, unidades, prazos, dados do comprador e condições expressas na mensagem.

regras de negócio:

- O assistente deve apontar as exigências do pedido e, se a mensagem citar um contrato disponível na base, também as exigências do contrato. Para cada exigência, deve indicar a fonte e o que o funcionário ainda precisa conferir.
- O assistente deve preservar a unidade informada e converter quantidades apenas quando houver equivalência conhecida.
- O assistente deve pedir esclarecimento quando a quantidade informada for agregada ou ambígua.

### RF04 - Classificar solicitações na triagem

O assistente deve classificar solicitações por tipo e urgência e sinalizar problemas, como sazonalidade desfavorável e quantidade acima da capacidade de fornecimento documentada.

regras de negócio:

- O assistente deve classificar a intenção principal como pedido, consulta, oferta, comunicado ou não identificado. Cotações e consultas de fornecimento, documentais e financeiras entram como consulta. A análise deve preservar as intenções adicionais da mensagem.
- A solicitação é urgente quando houver urgência declarada ou quando a entrega estiver prevista para o dia do recebimento ou o seguinte. Para um intervalo de entrega, o assistente deve considerar o primeiro dia.
- A urgência é normal quando a entrega estiver prevista para depois do dia seguinte ao recebimento e não houver urgência declarada. É indeterminada quando faltarem dados para classificar. O assistente deve registrar na análise o motivo da urgência.
- O assistente deve distinguir sazonalidade, capacidade estimada e disponibilidade confirmada. Deve comparar demanda e capacidade em unidades e períodos compatíveis. Capacidade e entregas anteriores não comprovam estoque atual.

### RF05 - Consultar documentos e dados da cooperativa

O assistente deve responder a consultas sobre certificações, rastreabilidade, sazonalidade, lotes e condições de fornecimento presentes nos documentos e dados da cooperativa.

regras de negócio:

- Antes de afirmar que um produto é orgânico, o assistente deve verificar se o certificado cobre o produto e está vigente na data de referência da consulta.
- O assistente deve preservar as unidades dos registros consultados. Para somar quantidades, deve usar a mesma unidade e converter apenas quando houver equivalência conhecida. Quantidades agregadas ou ambíguas exigem esclarecimento antes de entrar nos totais.
- Ao consultar preços e condições, o assistente deve informar a fonte, a vigência e as condições aplicáveis. Deve apontar divergências entre documentos e usar os preços de outubro de 2026 apenas para o período de vigência da tabela.

### RF06 - Identificar as fontes das respostas

O assistente deve identificar as fontes das respostas pelo documento e pelo registro ou trecho pertinente.

regras de negócio:

- Na triagem, o assistente deve indicar de onde vem cada exigência, identificando a mensagem do pedido, o contrato citado ou ambos, conforme o caso.
- Ao informar preços ou condições de fornecimento, o assistente deve associar a fonte ao período de vigência e às condições aplicáveis.

### RF07 - Informar lacunas e divergências nos dados

O assistente deve informar quando os dados forem ausentes, insuficientes ou conflitantes, sem inventar uma resposta.

regras de negócio:

- Quando a busca não encontrar registros, o assistente deve informar que a informação não foi encontrada, sem concluir que o fato nunca ocorreu.
- Se os documentos apresentarem preços ou condições diferentes, o assistente deve indicar em que divergem.

### RF08 - Gerar resumos por produtor

O assistente deve, quando solicitado, consultar e cruzar os dados da base para gerar resumos por produtor com vendas, fornecimentos realizados, pedidos alocados e pendências financeiras.

regras de negócio:

- O assistente deve usar os registros financeiros para selecionar as vendas pela data da transação e os pagamentos pela data registrada de pagamento, dentro do período solicitado.
- O assistente deve incluir nas pendências as vendas feitas até a data de referência cujo pagamento esteja ausente da base ou tenha data posterior à referência. Isso inclui vendas de períodos anteriores.
- O assistente deve distinguir as pendências vencidas das que vencem na data de referência ou depois.
- O assistente deve tratar o pagamento registrado como informação da base, sem usá-lo como comprovação de repasse bancário ao produtor.
- O assistente deve incluir os Lotes cuja data efetiva de entrega esteja no período solicitado, incluindo as datas inicial e final, e citar os registros de origem.
- O assistente deve incluir a alocação operacional no resumo se a entrega estiver prevista para o período solicitado ou se pelo menos um dia do intervalo de entrega cair nesse período.
- O assistente deve identificar os fornecimentos realizados e os previstos e informar as respectivas datas efetivas ou previstas de entrega.
- O assistente deve desconsiderar no resumo as alocações operacionais removidas após o cancelamento de um pedido e continuar incluindo os Lotes históricos correspondentes ao período solicitado.
- O assistente deve apresentar os totais de quantidades por produto e unidade, distinguindo os fornecimentos realizados e os previstos.
- O assistente deve usar conversões de quantidades apenas quando houver equivalência conhecida.
- O assistente deve apresentar quantidades agregadas ou ambíguas como pendências e pedir esclarecimento antes de incluí-las nos totais.
- O assistente deve usar as ferramentas da aplicação para obter os resultados dos cálculos e preservá-los ao redigir o resumo, conforme o RNF04.

### RF09 - Redigir notificações para produtores

O assistente deve redigir, quando solicitado, notificações para produtores sobre pedidos de seus produtos.

regras de negócio:

- Por padrão, o assistente deve deixar fora do rascunho documentos internos, documentos solicitados pelo remetente e dados pessoais ou bancários.

### RF10 - Manter o contexto da conversa

O assistente deve considerar as mensagens e os esclarecimentos anteriores da mesma conversa ao responder ao funcionário, inclusive quando ele reabrir uma conversa salva.

### RF11 - Receber mensagens dos canais integrados

O sistema deve receber mensagens de texto pelos canais integrados.

regras de negócio:

- O sistema deve registrar a resposta na conversa de uma solicitação ainda não finalizada quando houver vínculo confiável e a mensagem der continuidade à mesma demanda. O mesmo remetente ou a mesma conversa, por si só, não estabelece esse vínculo.
- O sistema deve iniciar nova triagem para demandas independentes, vínculos incertos ou respostas a solicitações finalizadas.

### RF12 - Exibir cartões na fila de triagem

O sistema deve exibir na fila de triagem um cartão por solicitação. O cartão deve mostrar o resumo, o tipo, a urgência e o estado atual da solicitação (recebida, em análise ou finalizada).

regras de negócio:

- O cartão deve mostrar o tipo da intenção principal e a urgência definidos na triagem.
- O cartão de uma ocorrência agendada deve representar a solicitação gerada para aquela ocorrência.
- O sistema deve atualizar o resumo, o tipo e a urgência do cartão quando esses dados forem afetados por uma resposta vinculada. A atualização deve preservar o estado do atendimento.

### RF13 - Esclarecer ambiguidades na triagem

O assistente deve fazer perguntas ao funcionário para esclarecer ambiguidades e atualizar a análise com as respostas, preservando a mensagem original.

regras de negócio:

- Ao pedir esclarecimento sobre uma quantidade agregada ou ambígua, o assistente deve indicar qual informação falta confirmar.
- Ao pedir esclarecimento sobre datas, o assistente deve indicar quais referências entram em conflito, como a data explícita e o dia da semana.

### RF14 - Sugerir produtores para o pedido

O assistente deve sugerir no chat produtores que possam atender ao pedido.

regras de negócio:

- Ao avaliar a certificação orgânica para um fornecimento futuro com prazo conhecido, o assistente deve verificar se o certificado cobre o produto e está vigente na data de entrega ou durante todo o intervalo.
- O assistente deve comparar a demanda com a capacidade em unidades e períodos compatíveis. Na sugestão, deve distinguir sazonalidade, capacidade estimada e disponibilidade confirmada. Capacidade estimada e entregas anteriores não comprovam estoque atual.
- O assistente deve excluir das sugestões os produtores inativos e os incompatíveis com as exigências do pedido ou do contrato citado, quando disponível na base. Deve apresentar separadamente os candidatos aptos e aqueles cuja aptidão ainda precisa ser comprovada.
- Se faltar fornecedor apto ou houver dados insuficientes, o assistente deve explicar o motivo no chat e manter a pendência para decisão do funcionário. Ao sugerir uma alternativa, deve indicar qual item ela substituiria e deixar a decisão com o funcionário.

### RF15 - Atualizar o estado da solicitação

O sistema deve criar cada solicitação no estado recebida, alterar seu estado para em análise quando o funcionário abrir o cartão pela primeira vez e para finalizada quando ele encerrar o atendimento.

regras de negócio:

- O funcionário pode encerrar a solicitação sem atendimento.

### RF16 - Autenticar o acesso do funcionário

O funcionário deve se autenticar para acessar o sistema.

### RF17 - Ler e baixar documentos citados

O funcionário deve poder ler o documento completo e baixar o arquivo original usado na resposta.

### RF18 - Baixar o resumo do produtor em PDF

O sistema deve oferecer a opção "Baixar resumo em PDF" junto a cada resumo por produtor, preservando o conteúdo e as fontes apresentados.

### RF19 - Gerenciar pedidos

O funcionário deve poder criar, consultar, editar e cancelar pedidos.

regras de negócio:

- Ao cancelar um pedido, o sistema deve marcá-lo como cancelado e excluir suas alocações operacionais na mesma operação. O pedido deve continuar disponível para consulta e os Lotes históricos devem ser preservados.
- Antes de salvar uma alteração que invalide alocações operacionais, o sistema deve exigir que o funcionário ajuste ou exclua as alocações afetadas.
- O sistema deve manter o pedido cancelado sem alocações operacionais, inclusive quando o cancelamento e o salvamento de uma alocação ocorrerem em paralelo.

### RF20 - Preparar rascunhos de pedidos no chat

O assistente deve preparar no chat um rascunho de pedido com comprador, itens, quantidades, unidades, prazo e condições de atendimento. O rascunho deve manter a data ou o intervalo de entrega informado pelo comprador. O horário pode ficar nas condições de entrega.

regras de negócio:

- O assistente deve sinalizar no rascunho os itens solicitados sob condição, como "se tiver", para que o funcionário decida quais entram no pedido.

### RF21 - Gerenciar agendamentos semanais

O funcionário deve poder cadastrar, consultar, editar e cancelar agendamentos semanais.

regras de negócio:

- O sistema deve aplicar alterações e cancelamentos da série apenas às ocorrências pendentes. As solicitações já geradas devem manter os dados originais.
- O sistema deve aplicar a mudança de dia a partir da semana de fornecimento da primeira ocorrência pendente. Para esse cálculo, a semana vai de segunda a domingo. Se já houver uma solicitação da série com fornecimento nessa semana, a mudança deve começar na semana seguinte.

### RF22 - Gerenciar alocações por item do pedido

O funcionário deve poder cadastrar, consultar, editar e excluir alocações operacionais por item do pedido. Cada alocação deve indicar o produtor, a quantidade e a unidade.

regras de negócio:

- O sistema deve bloquear o cadastro ou a edição de uma alocação para produtor inativo e informar o motivo ao funcionário.
- O funcionário deve confirmar a disponibilidade do produtor para o fornecimento antes de salvar a alocação.
- O sistema deve aceitar apenas quantidades positivas.
- Para somar as alocações, o sistema deve usar a unidade do item e converter quantidades apenas quando houver equivalência conhecida. Deve rejeitar o salvamento se a unidade for incompatível ou se o total ultrapassar a quantidade solicitada.
- O sistema deve aceitar o cadastro ou a edição da alocação apenas se o pedido estiver ativo no momento da gravação.
- O sistema deve validar a alocação no momento da gravação, usando os dados atuais do pedido, do item, do produtor e das demais alocações.

### RF23 - Preparar rascunhos de resposta ao remetente

O assistente, a pedido do funcionário, deve preparar um rascunho de resposta ao remetente.

regras de negócio:

- Por padrão, o assistente deve deixar fora do rascunho documentos internos, documentos solicitados pelo remetente e dados pessoais ou bancários.

### RF24 - Salvar os dados do agendamento semanal

O sistema, ao salvar um agendamento semanal, deve registrar o comprador, os itens, as quantidades, as unidades, as condições de atendimento confirmadas pelo funcionário, a primeira data de fornecimento e a antecedência da triagem em dias corridos.

### RF25 - Abrir a conversa da solicitação pelo cartão

O funcionário deve poder abrir, pelo cartão, a conversa vinculada à solicitação. Na conversa, deve poder consultar a análise inicial, as pendências identificadas e o texto original das mensagens recebidas, quando houver.

regras de negócio:

- O funcionário deve poder consultar na análise o motivo da urgência.
- Quando faltar fornecedor apto ou os dados forem insuficientes, a análise deve indicar o motivo da pendência para o funcionário decidir como seguir.
- Quando chegar uma resposta vinculada, o sistema deve atualizar a análise e as pendências na conversa e manter a análise inicial disponível no histórico.

### RF26 - Indicar o que falta confirmar sobre a disponibilidade

O assistente deve indicar no resumo o que o funcionário ainda precisa confirmar sobre a disponibilidade do produtor.

regras de negócio:

- No resumo, o assistente deve distinguir a disponibilidade confirmada dos dados de sazonalidade, das estimativas de capacidade e do histórico de entregas.

### RF27 - Considerar o saldo a alocar por item

O assistente deve, ao sugerir atendimento para um pedido cadastrado, obter pelas ferramentas da aplicação o saldo a alocar de cada item e usá-lo na sugestão.

regras de negócio:

- O assistente deve usar o saldo calculado pela quantidade solicitada menos o total das alocações operacionais vigentes daquele item no momento da consulta.
- O assistente deve obter o saldo na unidade do item. Conversões de quantidades alocadas em outras unidades devem ser usadas apenas quando houver equivalência conhecida.

### RF28 - Informar o motivo do bloqueio de exclusão

O sistema deve informar ao funcionário qual vínculo impede a operação quando bloquear uma exclusão.

regras de negócio:

- Quando uma citação impedir a exclusão de um documento, o sistema deve indicar qual citação bloqueia a exclusão.

### RF29 - Disponibilizar documentos após o processamento

O sistema deve disponibilizar os documentos adicionados pela aplicação para consulta e citação pelo assistente após o processamento.

### RF30 - Revisar e editar rascunhos no chat

O funcionário deve poder revisar e editar no chat os rascunhos de pedidos, agendamentos e alocações.

regras de negócio:

- Se uma resposta vinculada corrigir um dado usado em um rascunho de pedido aberto, o sistema deve mostrar a correção ao funcionário antes da confirmação. O funcionário decide se ajusta o rascunho.
- Ao revisar o rascunho de pedido, o funcionário deve decidir quais itens solicitados sob condição serão incluídos.
- Ao revisar o rascunho de alocação, o funcionário deve poder ajustar o pedido, o item, o produtor, a quantidade e a unidade. A confirmação de disponibilidade deve corresponder aos dados do fornecimento na versão revisada.

### RF31 - Cadastrar pedidos, agendamentos e alocações confirmados no chat

O sistema deve cadastrar a versão revisada do pedido, do agendamento ou da alocação após a confirmação explícita do funcionário no chat.

regras de negócio:

- Quando uma resposta vinculada corrigir dados de um rascunho de pedido, o pedido salvo deve refletir a decisão do funcionário sobre aplicar a correção.
- O sistema deve incluir no pedido somente os itens solicitados sob condição que o funcionário tiver aceitado na revisão.
- O sistema deve usar a mesma operação para cadastrar pedidos pelo chat e pelo cadastro direto. Essa exigência também se aplica ao cadastro de alocações.
- O sistema deve validar a alocação conforme o RF22, considerando as mudanças feitas enquanto o rascunho esteve aberto.
- Se alguma condição impedir o cadastro da alocação, o sistema deve informar o motivo no chat.
- O sistema deve aplicar o RNF03 às confirmações de alocações pelo chat, mantendo uma única alocação ao receber novamente a mesma confirmação.

### RF32 - Vincular o pedido à solicitação de origem

O sistema deve vincular o pedido cadastrado pelo chat da triagem à solicitação de origem. O funcionário deve poder abrir o pedido salvo pelo chat dessa solicitação.

### RF33 - Preparar rascunhos de agendamentos semanais

O assistente deve preparar no chat um rascunho de agendamento semanal com o comprador, os itens, as quantidades, as unidades, as condições de atendimento, a primeira data de fornecimento e a antecedência da triagem em dias corridos.

### RF34 - Editar e copiar rascunhos de mensagens

O funcionário deve poder editar e copiar o texto dos rascunhos de respostas e notificações.

regras de negócio:

- O sistema deve oferecer apenas revisão e cópia dos rascunhos de resposta às mensagens enviadas pelo script da apresentação.
- Quando o envio estiver indisponível, o sistema deve informar o motivo e oferecer a opção de copiar o rascunho.
- O sistema só deve permitir a cópia de um rascunho que contenha documentos internos, documentos solicitados pelo remetente ou dados pessoais ou bancários depois que o funcionário autorizar os dados ou trechos específicos para aquele destinatário.

### RF35 - Conferir destinatário e canal antes do envio

O sistema, quando o envio estiver disponível, deve mostrar o destinatário e o canal para o funcionário conferir antes de confirmar.

regras de negócio:

- O sistema só deve oferecer o envio de uma resposta quando a mensagem tiver chegado por um canal integrado, houver um destino válido e o canal permitir o envio. O canal a conferir é o de origem.
- Para uma notificação, o sistema deve mostrar o canal integrado escolhido pelo funcionário e o destino para conferência. Na demonstração, o envio fica disponível apenas para destinos de teste que a equipe vinculou ao produtor.
- A confirmação do funcionário deve autorizar explicitamente a versão revisada do texto para o destinatário e o canal conferidos.

### RF36 - Registrar envios no histórico do chat

O sistema deve registrar cada envio em uma mensagem no chat com o texto autorizado, o funcionário que confirmou o envio, o destinatário, o canal e o resultado do envio.

regras de negócio:

- O texto registrado no histórico deve corresponder à versão que o funcionário autorizou para o destinatário e o canal conferidos.
- Se uma tentativa terminar sem confirmação do resultado, o sistema deve mostrar "Resultado incerto" no histórico para conferência.

### RF37 - Alertar sobre pedidos de documentos ou dados

O assistente, quando o remetente pedir documentos, dados pessoais ou dados bancários, deve avisar o funcionário e indicar o que foi solicitado.

### RF38 - Gerenciar documentos

O funcionário deve poder listar, adicionar, abrir para leitura, baixar e excluir documentos na aplicação.

regras de negócio:

- O sistema deve bloquear a exclusão de um documento usado em uma citação.

### RF39 - Salvar o prazo de entrega do pedido

O sistema deve salvar o prazo de entrega como data única ou intervalo de datas ao cadastrar ou editar um pedido, conforme definido pelo funcionário.

### RF40 - Enviar respostas e notificações

O sistema deve enviar somente a versão do texto confirmada explicitamente pelo funcionário. O envio deve usar o destinatário e o canal integrado que o funcionário conferiu.

regras de negócio:

- A consulta de disponibilidade pode ser enviada antes de confirmar uma alocação, desde que o envio esteja disponível e o funcionário confirme o texto para o destinatário e o canal conferidos.
- O sistema só deve enviar texto que inclua documentos internos, documentos solicitados pelo remetente ou dados pessoais ou bancários depois que o funcionário autorizar os dados ou trechos específicos para aquele destinatário.
- O sistema deve aplicar o RF44 quando o texto confirmar fornecimento.
- O sistema deve seguir o RF45 para permitir uma nova tentativa de envio.

### RF41 - Carregar o histórico inicial de alocações

O sistema deve carregar os registros de `lotes.csv` como Lotes e disponibilizá-los para consulta do histórico de alocações.

regras de negócio:

- O sistema deve preservar o identificador original de cada lote.
- O sistema deve preservar os dados do produtor, produto, comprador e pedido histórico, a quantidade original e a unidade identificada, as datas de colheita, entrega e validade, a temperatura de transporte, a inspeção visual e as observações.
- O sistema deve identificar o arquivo e o registro de origem de cada Lote para permitir a conferência da informação.
- O sistema deve preservar a referência do pedido histórico quando seu cadastro original estiver ausente da base.
- O sistema deve manter como desconhecidos os dados ausentes, como a quantidade originalmente solicitada e o prazo combinado.
- O sistema deve aplicar o RNF06 à carga dos Lotes, incluindo o reaproveitamento dos registros ao repetir a carga, a preservação dos originais e o tratamento de unidades ambíguas.

### RF42 - Preparar rascunhos de alocações no chat

O assistente deve preparar no chat um rascunho de alocação que identifique o pedido cadastrado, o item, o produtor, a quantidade e a unidade.

regras de negócio:

- O assistente deve apresentar no rascunho a data ou o intervalo de entrega do pedido e indicar se o funcionário já confirmou a disponibilidade para aquele fornecimento.
- O assistente deve pedir esclarecimento antes de oferecer o cadastro quando faltar informação ou houver ambiguidade sobre o pedido, o item, o produtor, a quantidade ou a unidade.

### RF43 - Gerar solicitações dos agendamentos

O sistema deve gerar uma única solicitação vinculada ao agendamento para cada ocorrência quando chegar a data prevista para sua triagem.

regras de negócio:

- O sistema deve calcular a data de triagem de cada ocorrência subtraindo a antecedência em dias corridos da data de fornecimento.
- O sistema deve preservar na solicitação o comprador, os itens, as quantidades, as unidades, as condições de atendimento e a data de fornecimento daquela ocorrência.
- O sistema deve verificar as ocorrências pendentes ao retomar o serviço ou salvar um agendamento novo ou editado.
- O sistema deve gerar a solicitação de imediato para uma ocorrência pendente com triagem prevista para hoje ou antes e fornecimento previsto para hoje ou depois.
- O sistema deve marcar como perdida a ocorrência pendente cuja data de fornecimento já passou e seguir para a próxima.
- O sistema deve manter uma única solicitação por ocorrência, inclusive ao recuperar ocorrências pendentes.

### RF44 - Validar compromissos de fornecimento antes do envio

O sistema deve validar o compromisso quando o funcionário confirmar um texto que promete fornecimento e imediatamente antes de cada tentativa de envio.

regras de negócio:

- O sistema deve verificar se o pedido está ativo e se as alocações operacionais vigentes cobrem os itens, as quantidades, as unidades e os prazos prometidos.
- O sistema deve conferir as alocações operacionais do produtor que receberá a notificação e dos produtores indicados no texto como responsáveis pelo fornecimento.
- O sistema deve verificar, para entregas futuras, se esses produtores continuam ativos.
- O sistema deve verificar, para entregas futuras, se as comprovações dos produtores ou itens alocados atendem às exigências do pedido e do contrato citado, quando disponível na base. As comprovações devem estar vigentes na data prometida ou durante todo o intervalo prometido.
- O sistema deve bloquear o envio e informar o motivo quando houver impedimento para confirmar o compromisso.

### RF45 - Controlar novas tentativas de envio

O sistema só deve permitir uma nova tentativa de envio após confirmar a falha anterior e receber nova confirmação explícita do funcionário.

regras de negócio:

- O sistema deve bloquear novas tentativas enquanto houver um envio em andamento ou com resultado incerto.
- O sistema deve manter esse bloqueio quando o funcionário editar o rascunho.
- O sistema deve aplicar o RNF08 às confirmações repetidas ou simultâneas e o RF36 ao registro do resultado no histórico do chat.

### RF46 - Apresentar a alocação cadastrada pelo chat

O sistema deve apresentar no chat a alocação salva e permitir ao funcionário abrir o pedido correspondente para consultá-la.

### Notas gerais

Neste documento, "sistema" e "aplicação" designam o produto completo, que inclui a interface, os serviços e o assistente. As consultas aos registros, os cálculos, as validações, as gravações e os envios são executados pelos serviços da aplicação.

O assistente é a parte conversacional do sistema. Ele interpreta mensagens, pede esclarecimentos, apresenta sugestões e redige textos usando os dados e as ferramentas da aplicação. Pode acionar os serviços conforme as condições definidas nos requisitos.

O funcionário esclarece informações, revisa propostas, confirma a disponibilidade dos produtores e autoriza as operações que dependem de sua confirmação.

O Lote registra um fornecimento realizado. Sua data de entrega corresponde à data efetiva registrada na fonte. A quantidade originalmente solicitada e o prazo combinado com o comprador dependem de registros que informem esses dados.

As consultas documentais, financeiras e operacionais usam a mesma interface conversacional. Uma mensagem pode exigir várias consultas. A classificação não exige um fluxo ou agente separado para cada tipo.

O funcionário pode discutir as sugestões com o assistente e registrar as alocações na gestão do pedido ou revisar e confirmar um rascunho de alocação no chat.

O assistente apresenta os resumos e as notificações em texto. O funcionário pode copiá-los.

As regras de implementação das integrações estão em [Integrações](intregracoes.md).

O sistema deve usar o horário local da cooperativa, em Pernambuco, para interpretar datas de mensagens e calcular as datas da triagem e dos agendamentos.

Quando a consulta não informar uma data de referência, o assistente deve usar a data de recebimento da mensagem de origem ou a data da consulta, se ela tiver começado no chat. Deve informar na resposta qual data usou.

As restrições sanitárias e documentais adotadas pertencem ao cenário simulado.

## Requisitos não funcionais

| ID | Requisito e verificação |
| --- | --- |
| RNF01 | O sistema deve preservar mensagens, conversas, análises, documentos adicionados pela aplicação, pedidos, agendamentos, alocações e Lotes após fechar e reabrir a aplicação. O funcionário deve poder recuperar o histórico de envios no chat. |
| RNF02 | O sistema deve indicar processamento em andamento e avisar sobre a demora após 60 segundos sem conclusão. |
| RNF03 | O sistema deve evitar registros duplicados em novas tentativas da mesma operação, inclusive no recebimento de mensagens, na confirmação pelo chat, na geração de ocorrências agendadas e no cadastro de alocações. |
| RNF04 | O sistema deve calcular os valores financeiros a partir dos registros selecionados. O assistente deve preservar esses resultados ao redigir a resposta. |
| RNF05 | O sistema deve validar os tokens JWT das consultas e operações internas e rejeitar acessos sem token válido. Antes de processar eventos recebidos por webhook, deve validar sua autenticidade. |
| RNF06 | O sistema deve disponibilizar os dados e documentos fornecidos por uma carga reproduzível, preservando originais, identificadores e fontes. Deve preservar o valor e a descrição originais das quantidades. A unidade usada deve ser a explícita no registro, mesmo quando o nome da coluna indicar outra. O sistema deve sinalizar unidades ambíguas e manter essas quantidades fora de somas e conversões até esclarecê-las. Ao repetir a mesma carga, deve reaproveitar os registros existentes, manter as lacunas da fonte e preservar as exclusões de documentos feitas pela aplicação. |
| RNF07 | O sistema deve receber mensagens por uma interface comum de entrada, aplicando adaptadores quando necessário. |
| RNF08 | O sistema deve acionar no máximo uma tentativa de envio por confirmação, mesmo quando a receber mais de uma vez. O sistema deve tratar confirmações da mesma versão de um rascunho para o mesmo destinatário e canal como um único envio, inclusive quando ocorrerem em paralelo. |
| RNF09 | O sistema deve preservar a versão vigente do registro quando rejeitar uma alteração. |
| RNF10 | O sistema deve preservar análises e esclarecimentos mais recentes quando receber resultados atrasados de tentativas anteriores. |
| RNF11 | O sistema deve preservar a solicitação existente para permitir nova tentativa. Se a triagem ainda não tiver criado a solicitação, deve preservar o registro de entrada. Deve oferecer nova tentativa após o aviso de demora. Para envios, a nova tentativa deve seguir as condições do RF45. |

## Validação da entrega

Definir os resultados esperados antes de testar as 15 mensagens fornecidas e as consultas das três frentes. Conferir extração, classificação, perguntas de esclarecimento, fontes e reconhecimento de informação ausente ou conflitante.

Na apresentação, executar um script que lê as 15 mensagens de `pedidos.json`, prepara cada registro no formato esperado pela entrada do seu canal e faz uma requisição por mensagem. Verificar se as mensagens entram no fluxo normal de triagem.

Validar as operações dos CRUDs. Verificar o cadastro de um pedido pelo chat, a geração de uma ocorrência agendada e a consulta de uma alocação no resumo por produtor.

Carregar os 20 Lotes de `lotes.csv` e conferir os identificadores, os dados preservados e as fontes, conforme a US06. Repetir a carga da mesma base e verificar que os registros e as quantidades nos resumos permanecem iguais.

Consultar LOT-2026-0094 e conferir produtor, produto, quantidade, unidade, datas de colheita e entrega e referência do pedido histórico. Abrir e baixar o arquivo original pela citação. Consultar LOT-2026-0099 e verificar que a descrição "40 maços (kg)" permanece disponível, com a ambiguidade indicada e a quantidade fora de somas e conversões até esclarecimento.

Gerar o resumo de P004 para setembro de 2026 e conferir as 300 unidades de alface e os 150 maços de coentro entregues em 08/09/2026, com LOT-2026-0094 e LOT-2026-0095 como fontes. Repetir a consulta para os períodos de 08/09/2026 a 08/09/2026 e de 06/09/2026 a 06/09/2026, conferindo os resultados definidos na US07. Conferir a identificação e os totais dos fornecimentos realizados e previstos, a seleção pelas respectivas datas e a reprodução do conteúdo e das fontes no PDF.

Comparar os valores apresentados pelo assistente no resumo com os resultados retornados pelas ferramentas da aplicação e com os valores esperados a partir dos registros selecionados. Conferir as fontes citadas e verificar que quantidades agregadas ou ambíguas aparecem como pendências, com pedido de esclarecimento, e ficam fora dos totais até serem esclarecidas. Conferir que as conversões usam equivalências conhecidas.

Preparar um rascunho de alocação no chat, editar seus dados, confirmar a disponibilidade e autorizar o cadastro. Conferir a versão salva no chat, na gestão do pedido e no resumo do produtor para o período previsto de entrega. Repetir a mesma confirmação e verificar que existe uma única alocação. Validar os esclarecimentos e os bloqueios previstos na US17, incluindo pedido cancelado, produtor inativo, disponibilidade pendente, quantidade inválida, unidade incompatível, saldo insuficiente e ausência de autenticação válida.

Solicitar uma sugestão de atendimento para um pedido cadastrado e conferir que o assistente usa o saldo de cada item retornado pelas ferramentas da aplicação.

Manter um rascunho de alocação aberto e cadastrar outra alocação que consuma parte desse saldo. Comparar o saldo usado na sugestão com o saldo disponível no momento da gravação. Tentar confirmar uma quantidade superior ao saldo restante e verificar a rejeição com o motivo informado no chat.

Em outro cenário, cancelar o pedido enquanto o rascunho estiver aberto e conferir o bloqueio do cadastro. Verificar que o cancelamento remove as alocações operacionais e preserva os Lotes históricos nas consultas e nos resumos dos respectivos períodos.

Na aplicação publicada na nuvem, testar em cada canal integrado o recebimento de uma mensagem, a resposta ao remetente e a notificação a um produtor de teste. Conferir a revisão pelo funcionário e o histórico dos envios. Nos canais que usam webhook, verificar que o sistema rejeita eventos que falham na validação de autenticidade.

Com a equipe desconectada, enviar uma mensagem e aguardar uma ocorrência agendada. Ao voltar à aplicação, verificar que a análise da mensagem já está registrada e que a solicitação da ocorrência foi gerada na data prevista.

Executar os fluxos com um funcionário e a base completa. Medir os tempos de análise e consulta e registrar as condições da demonstração. O limite de espera do RNF02 não representa garantia de conclusão nesse prazo.

## Fora do escopo

- Acesso direto de produtores, compradores e auditores à plataforma.
- Alocações automáticas, controle de estoque e reservas, negociação comercial, acompanhamento de entregas e gestão de pagamentos.
