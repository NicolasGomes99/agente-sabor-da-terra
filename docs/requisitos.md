# Requisitos

## Escopo

O assistente é de uso interno da cooperativa fictícia Sabor da Terra. Ele analisa as solicitações que entram na triagem, responde a consultas sobre documentos e dados operacionais com indicação das fontes e prepara resumos e notificações para produtores a pedido dos funcionários. Os funcionários conduzem o atendimento a compradores, produtores e auditores e autorizam as respostas e notificações antes do envio pela aplicação.

A equipe consulta os dados e documentos da base fornecida pelo chat. A aplicação permite gerenciar pedidos e agendamentos semanais e registrar alocações de produtores por item do pedido.

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

O assistente deve, quando solicitado, gerar resumos por produtor com vendas, pedidos alocados e pendências financeiras.

regras de negócio:

- O sistema deve apurar as vendas pela data da transação e os pagamentos pela data registrada de pagamento, dentro do período solicitado.
- O sistema deve incluir nas pendências as vendas feitas até a data de referência cujo pagamento esteja ausente da base ou tenha data posterior à referência. Isso inclui vendas de períodos anteriores.
- O sistema deve separar as pendências vencidas das que vencem na data de referência ou depois.
- O assistente deve tratar o pagamento registrado como informação da base, sem usá-lo como comprovação de repasse bancário ao produtor.
- O sistema deve incluir a alocação no resumo se a entrega estiver prevista para o período solicitado ou se pelo menos um dia do intervalo de entrega cair nesse período.
- Após o cancelamento de um pedido, os próximos resumos devem omitir as alocações removidas.
- O sistema deve totalizar quantidades por produto e unidade, convertendo apenas quando houver equivalência conhecida. Quantidades agregadas ou ambíguas exigem esclarecimento antes de entrar nos totais.

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

- Ao cancelar um pedido, o sistema deve marcá-lo como cancelado e excluir suas alocações na mesma operação. O pedido deve continuar disponível para consulta.
- Antes de salvar uma alteração que invalide alocações, o sistema deve exigir que o funcionário ajuste ou exclua as alocações afetadas.
- O sistema deve manter o pedido cancelado sem alocações, inclusive quando o cancelamento e o salvamento de uma alocação ocorrerem em paralelo.

### RF20 - Preparar rascunhos de pedidos no chat

O assistente deve preparar no chat um rascunho de pedido com comprador, itens, quantidades, unidades, prazo e condições de atendimento. O rascunho deve manter a data ou o intervalo de entrega informado pelo comprador. O horário pode ficar nas condições de entrega.

regras de negócio:

- O assistente deve sinalizar no rascunho os itens solicitados sob condição, como "se tiver", para que o funcionário decida quais entram no pedido.

### RF21 - Gerenciar agendamentos semanais

O funcionário deve poder cadastrar, consultar, editar e cancelar agendamentos semanais.

regras de negócio:

- O sistema deve aplicar alterações e cancelamentos da série apenas às ocorrências pendentes. As solicitações já geradas devem manter os dados originais.
- Ao mudar o dia de fornecimento, o novo dia vale a partir da semana de fornecimento da primeira ocorrência pendente. A semana vai de segunda a domingo. Se já houver uma solicitação da série com fornecimento naquela semana, a mudança vale a partir da semana seguinte.

### RF22 - Gerenciar alocações por item do pedido

O funcionário deve poder cadastrar, consultar, editar e excluir alocações por item do pedido. Cada alocação deve indicar o produtor, a quantidade e a unidade.

regras de negócio:

- O sistema deve bloquear o cadastro ou a edição de uma alocação para produtor inativo e informar o motivo ao funcionário.
- O funcionário deve confirmar a disponibilidade do produtor para o fornecimento antes de salvar a alocação.
- O sistema deve aceitar apenas quantidades positivas.
- Para somar as alocações, o sistema deve usar a unidade do item e converter quantidades apenas quando houver equivalência conhecida. Deve rejeitar o salvamento se a unidade for incompatível ou se o total ultrapassar a quantidade solicitada.
- O sistema deve aceitar o cadastro ou a edição da alocação apenas se o pedido estiver ativo no momento da gravação.

### RF23 - Preparar rascunhos de resposta ao remetente

O assistente, a pedido do funcionário, deve preparar um rascunho de resposta ao remetente.

regras de negócio:

- Por padrão, o assistente deve deixar fora do rascunho documentos internos, documentos solicitados pelo remetente e dados pessoais ou bancários.

### RF24 - Salvar os dados do agendamento semanal

O sistema, ao salvar um agendamento semanal, deve registrar o comprador, os itens, as quantidades, as unidades, as condições de atendimento confirmadas pelo funcionário, a primeira data de fornecimento e a antecedência da triagem em dias corridos.

regras de negócio:

- O sistema deve calcular a data de triagem de cada ocorrência subtraindo a antecedência em dias corridos da data de fornecimento. Na data prevista, deve gerar uma única solicitação vinculada ao agendamento.
- Ao gerar a solicitação, o sistema deve preservar o comprador, os itens, as quantidades, as unidades, as condições de atendimento e a data de fornecimento daquela ocorrência.
- Ao retomar o serviço ou salvar um agendamento novo ou editado, o sistema deve verificar as ocorrências pendentes com triagem prevista para hoje ou antes. Se o fornecimento estiver previsto para hoje ou depois, deve gerar a solicitação de imediato. Se a data de fornecimento já tiver passado, deve marcar a ocorrência como perdida e seguir para a próxima.

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

Ao sugerir atendimento para um pedido cadastrado, o assistente deve considerar, para cada item, a quantidade solicitada menos a quantidade já alocada.

regras de negócio:

- O assistente deve calcular o saldo na unidade do item. Se uma alocação estiver em outra unidade, deve convertê-la apenas quando houver equivalência conhecida.

### RF28 - Informar o motivo do bloqueio de exclusão

Ao bloquear uma exclusão, o sistema deve informar ao funcionário qual vínculo impede a operação.

regras de negócio:

- Quando uma citação impedir a exclusão de um documento, o sistema deve indicar qual citação bloqueia a exclusão.

### RF29 - Disponibilizar documentos após o processamento

O sistema deve disponibilizar os documentos adicionados pela aplicação para consulta e citação pelo assistente após o processamento.

### RF30 - Revisar e editar rascunhos no chat

O funcionário deve poder revisar e editar no chat os rascunhos de pedidos e agendamentos.

regras de negócio:

- Se uma resposta vinculada corrigir um dado usado em um rascunho de pedido aberto, o sistema deve mostrar a correção ao funcionário antes da confirmação. O funcionário decide se ajusta o rascunho.
- Ao revisar o rascunho de pedido, o funcionário deve decidir quais itens solicitados sob condição serão incluídos.

### RF31 - Cadastrar pedidos e agendamentos confirmados no chat

O sistema deve cadastrar a versão revisada do pedido ou do agendamento após a confirmação explícita do funcionário no chat. O sistema deve usar a mesma operação para cadastrar pedidos pelo chat e pelo cadastro direto.

regras de negócio:

- Quando uma resposta vinculada corrigir dados de um rascunho de pedido, o pedido salvo deve refletir a decisão do funcionário sobre aplicar a correção.
- O sistema deve incluir no pedido somente os itens solicitados sob condição que o funcionário tiver aceitado na revisão.

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

Ao cadastrar ou editar um pedido, o sistema deve salvar o prazo de entrega como data única ou intervalo de datas, conforme definido pelo funcionário.

### RF40 - Enviar respostas e notificações

O sistema deve enviar somente a versão do texto confirmada explicitamente pelo funcionário. O envio deve usar o destinatário e o canal integrado que o funcionário conferiu.

regras de negócio:

- A consulta de disponibilidade pode ser enviada antes de confirmar uma alocação, desde que o envio esteja disponível e o funcionário confirme o texto para o destinatário e o canal conferidos.
- O sistema só deve enviar texto que inclua documentos internos, documentos solicitados pelo remetente ou dados pessoais ou bancários depois que o funcionário autorizar os dados ou trechos específicos para aquele destinatário.
- Quando o texto confirmar fornecimento, o sistema deve validar o compromisso na confirmação do funcionário e imediatamente antes de cada tentativa de envio. Se o compromisso for inválido, deve bloquear o envio e informar o motivo.
- Para validar o compromisso, o sistema deve verificar se o pedido está ativo e se as alocações vigentes cobrem os itens, as quantidades, as unidades e os prazos prometidos. Deve conferir as alocações do produtor destinatário da notificação e dos produtores identificados no texto como responsáveis pelo fornecimento.
- Para fornecimento futuro, o sistema deve verificar se esses produtores continuam ativos. As comprovações aplicáveis aos produtores ou itens alocados devem atender às exigências do pedido e do contrato citado, quando disponível na base, e estar vigentes na data prometida ou durante todo o intervalo prometido.
- O sistema só deve permitir uma nova tentativa de envio após confirmar a falha anterior e receber nova confirmação explícita do funcionário. Deve manter o reenvio bloqueado enquanto houver uma tentativa em andamento ou com resultado incerto, mesmo se o funcionário editar o rascunho.

### Notas gerais

As consultas documentais, financeiras e operacionais usam a mesma interface conversacional. Uma mensagem pode exigir várias consultas. A classificação não exige um fluxo ou agente separado para cada tipo.

O funcionário pode discutir as sugestões com o assistente no chat. Ele decide e registra as alocações na gestão do pedido.

O assistente apresenta os resumos e as notificações em texto. O funcionário pode copiá-los.

As regras de implementação das integrações estão em [Integrações](intregracoes.md).

O sistema deve usar o horário local da cooperativa, em Pernambuco, para interpretar datas de mensagens e calcular as datas da triagem e dos agendamentos.

Quando a consulta não informar uma data de referência, o assistente deve usar a data de recebimento da mensagem de origem ou a data da consulta, se ela tiver começado no chat. Deve informar na resposta qual data usou.

As restrições sanitárias e documentais adotadas pertencem ao cenário simulado.

## Requisitos não funcionais

| ID | Requisito e verificação |
| --- | --- |
| RNF01 | O sistema deve preservar mensagens, conversas, análises, documentos adicionados pela aplicação, pedidos, agendamentos e alocações após fechar e reabrir a aplicação. O funcionário deve poder recuperar o histórico de envios no chat. Verificar que a retomada mantém os dados e separa o contexto de cada solicitação. |
| RNF02 | O sistema deve indicar processamento em andamento e avisar sobre a demora após 60 segundos sem conclusão. O sistema deve preservar a solicitação existente. Se a triagem ainda não tiver criado a solicitação, deve preservar o registro de entrada para permitir nova tentativa. Para envios, a nova tentativa segue as condições do RF40. Nas demais operações, o sistema deve oferecer nova tentativa após o aviso de demora. Verificar também o tratamento de falha do modelo ou das consultas. |
| RNF03 | O sistema deve evitar registros duplicados em novas tentativas da mesma operação, inclusive no recebimento de mensagens, na confirmação pelo chat, na geração de ocorrências agendadas e no cadastro de alocações. |
| RNF04 | Executar cálculos financeiros sobre os registros selecionados e conferir os resultados com valores esperados. A redação pelo modelo deve preservar esses resultados. |
| RNF05 | Proteger consultas e operações internas com validação de tokens JWT, rejeitando acessos sem token válido. Validar a autenticidade dos eventos recebidos por webhook antes de processá-los. |
| RNF06 | O sistema deve disponibilizar os dados e documentos fornecidos por uma carga reproduzível que preserve originais, identificadores e fontes. A carga deve preservar o valor e a descrição originais das quantidades e usar a unidade explícita no registro mesmo quando o nome da coluna indicar outra. O sistema deve sinalizar unidades ambíguas e manter essas quantidades fora de somas e conversões até esclarecê-las. Ao repetir a mesma carga, o sistema deve reaproveitar os registros existentes, manter as lacunas da fonte e preservar as exclusões de documentos feitas pela aplicação. |
| RNF07 | O sistema deve receber mensagens por uma interface comum de entrada, aplicando adaptadores quando necessário. |
| RNF08 | O sistema deve acionar no máximo uma tentativa de envio por confirmação, mesmo quando a receber mais de uma vez. O sistema deve tratar confirmações da mesma versão de um rascunho para o mesmo destinatário e canal como um único envio, inclusive quando ocorrerem em paralelo. |
| RNF09 | O sistema deve preservar a versão vigente do registro quando rejeitar uma alteração. |
| RNF10 | O sistema deve preservar análises e esclarecimentos mais recentes quando receber resultados atrasados de tentativas anteriores. |

## Validação da entrega

Definir os resultados esperados antes de testar as 15 mensagens fornecidas e as consultas das três frentes. Conferir extração, classificação, perguntas de esclarecimento, fontes e reconhecimento de informação ausente ou conflitante.

Na apresentação, executar um script que lê as 15 mensagens de `pedidos.json`, prepara cada registro no formato esperado pela entrada do seu canal e faz uma requisição por mensagem. Verificar se as mensagens entram no fluxo normal de triagem.

Validar as operações dos CRUDs. Verificar o cadastro de um pedido pelo chat, a geração de uma ocorrência agendada e a consulta de uma alocação no resumo por produtor.

Na aplicação publicada na nuvem, testar em cada canal integrado o recebimento de uma mensagem, a resposta ao remetente e a notificação a um produtor de teste. Conferir a revisão pelo funcionário e o histórico dos envios. Nos canais que usam webhook, verificar que o sistema rejeita eventos que falham na validação de autenticidade.

Com a equipe desconectada, enviar uma mensagem e aguardar uma ocorrência agendada. Ao voltar à aplicação, verificar que a análise da mensagem já está registrada e que a solicitação da ocorrência foi gerada na data prevista.

Executar os fluxos com um funcionário e a base completa. Medir os tempos de análise e consulta e registrar as condições da demonstração. O limite de espera do RNF02 não representa garantia de conclusão nesse prazo.

## Fora do escopo

- Acesso direto de produtores, compradores e auditores à plataforma.
- Alocações automáticas, controle de estoque e reservas, negociação comercial, acompanhamento de entregas e gestão de pagamentos.
