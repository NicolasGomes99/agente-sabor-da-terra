# Requisitos

## Escopo

Assistente interno para a equipe da cooperativa fictícia Sabor da Terra, com três frentes: triagem de pedidos, consulta a documentos e dados operacionais e comunicação com produtores. Compradores, produtores e auditores são atendidos pelos funcionários.

O cenário prevê de 60 a 100 pedidos diários por e-mail, formulário web e mensagens de texto. A entrega usa os 18 produtores, as 15 mensagens e os demais arquivos fornecidos. Esses números descrevem o cenário e a base de demonstração, sem estabelecer limites de capacidade do sistema.

Fonte: Projeto Intermediário - Formação Sauter.pdf, seções 3 a 6, e dados simulados da cooperativa. Os critérios de aceitação estão em [User stories](user-stories.md).

## Requisitos funcionais do enunciado

| ID | Requisito |
| --- | --- |
| RF01 | Permitir que o funcionário converse com o assistente por texto. |
| RF02 | Interpretar pedidos em português coloquial, com abreviações, erros de digitação, informações implícitas e ambiguidades. No protótipo, interpretar também a mensagem em inglês da base e apresentar a triagem em português. |
| RF03 | Extrair e organizar produtos, quantidades, unidades, prazos, dados do comprador e condições expressas na mensagem. |
| RF04 | Classificar solicitações por tipo e urgência e sinalizar problemas, incluindo sazonalidade desfavorável e quantidade acima da capacidade documentada. |
| RF05 | Responder a consultas sobre certificações, rastreabilidade, sazonalidade, lotes e condições de fornecimento presentes nos documentos e dados da cooperativa. |
| RF06 | Identificar as fontes das respostas pelo documento e pelo registro ou trecho pertinente. |
| RF07 | Informar quando os dados forem ausentes, insuficientes ou conflitantes, sem inventar uma resposta. |
| RF08 | Gerar, quando solicitado, resumos por produtor com vendas, pedidos alocados e pendências financeiras. |
| RF09 | Redigir, quando solicitado, notificações para produtores sobre pedidos de seus produtos. |
| RF10 | Manter o contexto de cada conversa durante a sessão. |

## Funcionalidades definidas para o protótipo

| ID | Requisito |
| --- | --- |
| RF11 | Receber mensagens de texto pelo ponto de entrada da aplicação e pelos canais integrados. Usar o mesmo fluxo de triagem para essas mensagens e para as importadas da base. Preservar o identificador de origem, o texto, o remetente, o canal e a data de recebimento. Identificar as mensagens importadas como parte da amostra. |
| RF12 | Apresentar cada solicitação em um cartão com resumo, classificação e pendências. Ao expandi-lo, exibir a análise inicial do agente, a conversa com o funcionário e o texto original das mensagens recebidas, quando houver. |
| RF13 | Fazer perguntas ao funcionário para esclarecer ambiguidades e atualizar a análise com as respostas, preservando a mensagem original. |
| RF14 | Apresentar e discutir no chat sugestões de atendimento com produtores candidatos, quantidades quando justificáveis, fontes e pendências de disponibilidade. Para pedidos cadastrados, considerar o saldo de cada item com base nas alocações registradas. |
| RF15 | Acompanhar solicitações nos estados recebida, em análise, aguardando informações, pronta para decisão e encerrada. No encerramento, registrar o resultado da triagem. |
| RF16 | Autenticar funcionários para acessar consultas e operações internas, com um único perfil de acesso no protótipo. |
| RF17 | Permitir ao funcionário ler o documento completo e baixar o arquivo original usado na resposta. A citação continua apontando para esse arquivo após a substituição do documento no cadastro. |
| RF18 | Oferecer a opção "Baixar resumo em PDF" junto a cada resumo por produtor, preservando o conteúdo e as fontes apresentados. |
| RF19 | Permitir ao funcionário cadastrar, consultar, editar e excluir produtores, produtos e documentos. Bloquear a exclusão de registros vinculados a pedidos, alocações, agendamentos, lotes, transações financeiras ou citações. Informar qual vínculo impede a exclusão. O assistente usa os dados atualizados nas consultas e sugestões. |
| RF20 | Permitir ao funcionário criar, consultar, editar e cancelar pedidos. Ao salvar o pedido, registrar as condições de atendimento que o funcionário confirmou para o pedido inteiro ou para itens específicos. Se um item depender de uma condição como "se tiver", o funcionário decide se ele entra no pedido. Quando o cadastro partir da triagem, vincular o pedido à solicitação de origem. |
| RF21 | Preparar no chat um rascunho com comprador, itens, quantidades, unidades, prazo e condições de atendimento. O funcionário pode revisar e ajustar os dados. Após a confirmação explícita, cadastrar a versão revisada pela mesma operação do CRUD. |
| RF22 | Permitir ao funcionário cadastrar, consultar, editar e cancelar agendamentos semanais. Registrar a primeira data de fornecimento e a antecedência da triagem em dias corridos, além dos dados do pedido e das condições de atendimento confirmadas pelo funcionário. O assistente também pode preparar o rascunho no chat e cadastrar o agendamento após a confirmação explícita do funcionário. |
| RF23 | Permitir ao funcionário cadastrar, consultar, alterar e excluir alocações por item do pedido, indicando produtor, quantidade e unidade. |
| RF24 | Preparar respostas aos remetentes. Se a mensagem pedir documentos, dados pessoais ou dados bancários, avisar o funcionário e deixar esse material fora do rascunho externo até que ele decida o que compartilhar. Permitir que o funcionário edite o rascunho da resposta ou da notificação ao produtor e copie o texto da resposta. Quando o envio estiver disponível conforme a RN17, o funcionário confere o destinatário e o canal antes de confirmar. Enviar o texto revisado após confirmação explícita e registrar no histórico o texto autorizado, o funcionário, o destinatário, o canal e o resultado do envio. |

As consultas documentais, financeiras e operacionais usam a mesma interface conversacional. Uma mensagem pode exigir várias consultas. A classificação não exige um fluxo ou agente separado para cada tipo.

O assistente sugere opções de atendimento no chat. O funcionário decide e registra as alocações no CRUD do pedido.

Resumos e notificações são apresentados em texto, com possibilidade de cópia.

O protótipo integra e-mail e WhatsApp. O Telegram pode substituir o WhatsApp na demonstração se o teste com a integração da Meta não atender ao fluxo previsto. As opções de implementação estão em [Integrações](intregrations.md).

## Regras de negócio

| ID | Regra |
| --- | --- |
| RN01 | Para afirmar que um produto é orgânico, verificar os produtos cobertos e a validade do certificado na data de referência. Para atendimento futuro, considerar a data de fornecimento quando conhecida. |
| RN02 | Excluir das sugestões produtores inativos ou incompatíveis com as restrições sanitárias ou exigências documentais do pedido. Documento obrigatório ausente deixa a aptidão sem comprovação. |
| RN03 | Preservar unidades e converter apenas com equivalência conhecida. Quantidades agregadas ou ambíguas exigem esclarecimento; valores em kg, maços, unidades e dúzias não podem ser somados como uma única medida. |
| RN04 | Distinguir sazonalidade, capacidade estimada e disponibilidade confirmada. Comparar quantidades apenas com unidades e períodos compatíveis. Capacidade e entregas anteriores não comprovam estoque atual. |
| RN05 | Ao consultar preços e condições, informar a fonte, o período de vigência e as condições aplicáveis. Expor divergências entre documentos. Preços de outubro de 2026 não comprovam preços de outros períodos. |
| RN06 | Interpretar datas relativas pela data de recebimento da mensagem em que aparecem. Pedir esclarecimento quando data explícita, dia da semana ou outras referências se contradisserem. |
| RN07 | Classificar como pedido de compra, cotação ou consulta de fornecimento, consulta documental, consulta financeira, oferta de produtor, comunicação administrativa ou não identificado. Preservar intenções adicionais da mesma mensagem. |
| RN08 | Sinalizar urgência declarada ou entrega para o dia do recebimento ou o seguinte, indicando o motivo. Usar normal quando houver prazo posterior sem urgência declarada e indeterminada quando faltarem elementos. Ao consultar a triagem, sinalizar separadamente se o prazo já venceu nessa data. |
| RN09 | No período solicitado, apurar vendas pela data das transações, pagamentos registrados pela data do pagamento e alocações pela previsão de fornecimento. Apurar as pendências na data de referência, incluindo dívidas de períodos anteriores, e separar as vencidas das que ainda vão vencer. O registro de pagamento não comprova repasse bancário ao produtor. |
| RN10 | Sem fornecedor apto ou dados suficientes, apresentar o motivo e manter a pendência para decisão do funcionário. Alternativas não podem substituir silenciosamente os itens solicitados. O funcionário pode encerrar a solicitação sem atendimento. |
| RN11 | Distinguir consulta de disponibilidade de compromisso de fornecimento. Ao confirmar ou repetir o envio de uma notificação de compromisso, verificar se a alocação ainda existe e se produtor, item, quantidade e prazo correspondem ao rascunho. Para fornecimento futuro, verificar também se a aptidão do produtor segue comprovada. Se o pedido tiver sido cancelado ou a verificação falhar, bloquear o envio e informar o motivo. Um rascunho atualizado exige nova confirmação. |
| RN12 | Aplicar no cadastro e na edição de alocações os critérios de aptidão da triagem. Comprovar as exigências obrigatórias, inclusive as sanitárias, contratuais e documentais que não constem do pedido, para o produtor, o item e a data de fornecimento, conforme o caso. O número de um registro, por si só, não comprova vigência. Se faltar comprovação, indicar a pendência e bloquear a alocação até que o funcionário registre a evidência. Antes de salvar, obter a confirmação de disponibilidade do funcionário. |
| RN13 | Usar quantidades positivas e unidades compatíveis. Limitar a soma das alocações por item à quantidade solicitada. |
| RN14 | Exigir o ajuste ou a exclusão das alocações afetadas antes de salvar uma alteração do pedido que as invalide. No cancelamento, marcar o pedido como cancelado e excluir suas alocações na mesma operação. Manter o pedido disponível para consulta e retirar essas alocações dos próximos resumos do produtor. |
| RN15 | Na data programada para triagem, gerar uma única solicitação por ocorrência, vinculada ao agendamento. A solicitação inclui comprador, itens, quantidades, unidades, condições de atendimento e data de fornecimento. Ao retomar o serviço ou salvar um agendamento novo ou editado, verificar as ocorrências pendentes cuja data de triagem já passou. Gerar a solicitação de imediato se o fornecimento for hoje ou depois. Se a data de fornecimento já passou, registrar a ocorrência como perdida e seguir com a próxima. Alterações e cancelamentos da série afetam apenas ocorrências pendentes. |
| RN16 | Acrescentar a resposta ao histórico da solicitação aberta quando houver vínculo confiável e atualizar a análise e as pendências. Se uma resposta vinculada corrigir um dado usado em um rascunho de pedido aberto, mostrar a correção ao funcionário antes da confirmação. O funcionário decide se ajusta o rascunho. O mesmo remetente ou a mesma conversa, por si só, não estabelece esse vínculo. Iniciar nova triagem para demandas independentes, vínculos incertos ou respostas a solicitações encerradas. |
| RN17 | Para responder a mensagens da amostra, oferecer apenas revisão e cópia do rascunho. Para enviar uma resposta pela aplicação, a mensagem precisa ter chegado por um canal integrado, ter um destino válido e atender às condições de envio do canal. Enviar pelo canal de origem após a confirmação explícita do funcionário. Para notificações, usar o canal integrado escolhido pelo funcionário e o destino conferido na revisão. Na demonstração, enviar notificações apenas para destinos de teste vinculados pela equipe ao produtor. Se o envio de uma resposta ou notificação estiver indisponível, informar o motivo e oferecer o rascunho para cópia. |
| RN18 | Permitir nova tentativa após falha confirmada de envio. Se o resultado for incerto, indicá-lo para conferência antes de permitir o reenvio. |

Quando a consulta não trouxer uma data de referência, usar a data de recebimento da mensagem de origem. Se o funcionário iniciar a consulta no chat, usar a data da consulta. Informar na resposta qual data foi usada. A ausência de registros deve ser apresentada como informação não encontrada, sem concluir que o fato nunca ocorreu. As restrições sanitárias e documentais adotadas pertencem ao cenário simulado.

## Requisitos não funcionais

| ID | Requisito e verificação |
| --- | --- |
| RNF01 | Preservar mensagens, histórico de envios, conversas, análises, cadastros, pedidos, agendamentos e alocações após fechar e reabrir a aplicação. Verificar que a retomada mantém os dados e separa o contexto de cada solicitação. |
| RNF02 | Indicar processamento em andamento. Após 60 segundos sem conclusão, informar a demora e permitir nova tentativa, preservando a solicitação. Para envios, a nova tentativa segue a RN18. Verificar também o tratamento de falha do modelo ou das consultas. |
| RNF03 | Evitar registros duplicados em novas tentativas da mesma operação, inclusive no recebimento de mensagens, na confirmação pelo chat, na geração de ocorrências agendadas e no cadastro de alocações. Cada confirmação de envio deve acionar uma única tentativa, mesmo quando recebida mais de uma vez. Uma alteração rejeitada deve preservar o registro anterior. Resultados de tentativas anteriores não podem sobrescrever análises ou esclarecimentos mais recentes. |
| RNF04 | Executar cálculos financeiros sobre os registros selecionados e conferir os resultados com valores esperados. A redação pelo modelo deve preservar esses resultados. |
| RNF05 | Proteger consultas e operações internas com validação de tokens JWT, rejeitando acessos sem token válido. Validar a autenticidade dos eventos recebidos por webhook antes de processá-los. |
| RNF06 | Disponibilizar os dados e documentos fornecidos por uma carga reproduzível que preserve originais, identificadores e fontes. Preservar o valor e a descrição originais das quantidades. Usar a unidade explícita no registro mesmo quando o nome da coluna indicar outra. Sinalizar unidades ambíguas e manter essas quantidades fora de somas e conversões até esclarecê-las. Repetir a carga sem duplicar registros nem preencher lacunas com dados fictícios. Na mesma base, a recarga preserva as edições e exclusões feitas no CRUD. Reaproveitar cada mensagem da amostra pelo identificador original. |
| RNF07 | Integrar os canais por adaptadores com uma interface comum. Usar essa interface para conectar novos canais à triagem e, quando houver suporte a envio, ao fluxo de revisão e aprovação. |

## Validação da entrega

Verificar as 15 mensagens fornecidas e consultas das três frentes com resultados esperados definidos antes dos testes. Conferir extração, classificação, perguntas de esclarecimento, fontes e reconhecimento de informação ausente ou conflitante.

Validar as operações dos CRUDs. Verificar o cadastro de um pedido pelo chat, a geração de uma ocorrência agendada e a consulta de uma alocação no resumo por produtor.

Na aplicação publicada na nuvem, testar em cada canal integrado o recebimento de uma mensagem, a resposta ao remetente e a notificação a um produtor de teste. Conferir a revisão pelo funcionário e o histórico dos envios. Verificar que uma mensagem recebida entra na triagem e que uma ocorrência é gerada na data prevista mesmo sem funcionário conectado.

Executar os fluxos com um funcionário e a base completa. Medir os tempos de análise e consulta e registrar as condições da demonstração. O limite de espera do RNF02 não representa garantia de conclusão nesse prazo.

## Fora do escopo

- Acesso direto de produtores, compradores e auditores à plataforma.
- Alocações automáticas, controle de estoque e reservas, negociação comercial, acompanhamento de entregas e gestão de pagamentos.
