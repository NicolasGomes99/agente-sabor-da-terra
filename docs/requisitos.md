# Requisitos

## Escopo

Assistente interno para a equipe da cooperativa fictícia Sabor da Terra, com três frentes: triagem de pedidos, consulta a documentos e dados operacionais e comunicação com produtores. Compradores, produtores e auditores são atendidos pelos funcionários.

O cenário prevê de 60 a 100 pedidos diários por e-mail, formulário web e mensagens de texto. A entrega usa os 18 produtores, as 15 mensagens e os demais arquivos fornecidos. Esses números descrevem o cenário e a base de demonstração, sem estabelecer limites de capacidade do sistema.

Fonte: Projeto Intermediário - Formação Sauter.pdf, seções 3 a 6, e dados simulados da cooperativa. Os critérios de aceitação estão em [User stories](user-stories.md).

## Requisitos funcionais do enunciado

| ID | Requisito |
| --- | --- |
| RF01 | Permitir que o funcionário converse com o assistente por texto. |
| RF02 | Interpretar pedidos em português coloquial, com abreviações, erros de digitação, informações implícitas e ambiguidades. |
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
| RF11 | Receber mensagens pelo ponto de entrada da aplicação, com identificador, texto original, remetente, canal e data de recebimento. |
| RF12 | Apresentar cada solicitação em um cartão com resumo, classificação e pendências. Ao expandi-lo, exibir a análise inicial do agente, a mensagem original e a conversa com o funcionário. |
| RF13 | Fazer perguntas ao funcionário para esclarecer ambiguidades e atualizar a análise com as respostas, preservando a mensagem original. |
| RF14 | Apresentar uma sugestão de atendimento com produtores candidatos, quantidades quando justificáveis, fontes e pendências de disponibilidade. Permitir discutir alternativas no chat. |
| RF15 | Acompanhar solicitações nos estados recebida, em análise, aguardando informações, pronta para decisão e encerrada. No encerramento, registrar o resultado da triagem. |
| RF16 | Autenticar funcionários para acessar consultas e operações internas, com um único perfil de acesso no protótipo. |
| RF17 | Permitir ao funcionário visualizar os documentos completos citados nas respostas e baixar seus arquivos originais. |
| RF18 | Oferecer a opção "Baixar resumo em PDF" junto a cada resumo por produtor, preservando o conteúdo e as fontes apresentados. |

As consultas documentais, financeiras e operacionais usam a mesma interface conversacional. Uma mensagem pode exigir várias consultas. A classificação não exige um fluxo ou agente separado para cada tipo.

O funcionário decide o atendimento. O protótipo apresenta sugestões, sem registrar ou alterar alocações. Sugestões não comprovam reserva de estoque, entrega ou pagamento.

Resumos e notificações são apresentados em texto, com possibilidade de cópia. O funcionário revisa e encaminha comunicações externas.

## Regras de negócio

| ID | Regra |
| --- | --- |
| RN01 | Para afirmar que um produto é orgânico, verificar os produtos cobertos e a validade do certificado na data de referência. Para atendimento futuro, considerar a data de fornecimento quando conhecida. |
| RN02 | Excluir das sugestões produtores inativos ou incompatíveis com as restrições sanitárias ou exigências documentais do pedido. Documento obrigatório ausente deixa a aptidão sem comprovação. |
| RN03 | Preservar unidades e converter apenas com equivalência conhecida. Quantidades agregadas ou ambíguas exigem esclarecimento; valores em kg, maços, unidades e dúzias não podem ser somados como uma única medida. |
| RN04 | Distinguir sazonalidade, capacidade estimada e disponibilidade confirmada. Comparar quantidades apenas com unidades e períodos compatíveis. Capacidade e entregas anteriores não comprovam estoque atual. |
| RN05 | Ao consultar preços e condições, informar a fonte, o período de vigência e as condições aplicáveis. Expor divergências entre documentos. Preços de outubro de 2026 não comprovam preços de outros períodos. |
| RN06 | Interpretar datas relativas a partir do recebimento da mensagem. Pedir esclarecimento quando data explícita, dia da semana ou outras referências se contradisserem. |
| RN07 | Classificar como pedido de compra, cotação ou consulta de fornecimento, consulta documental, consulta financeira, oferta de produtor, comunicação administrativa ou não identificado. Preservar intenções adicionais da mesma mensagem. |
| RN08 | Sinalizar urgência declarada ou entrega para o dia do recebimento ou o seguinte, indicando o motivo. Usar normal quando houver prazo posterior sem urgência declarada e indeterminada quando faltarem elementos. Sinalizar prazo vencido separadamente. |
| RN09 | Apurar vendas pela data das transações no período solicitado. Separar pagamentos registrados, pendências vencidas e a vencer na data de referência, incluindo dívidas de períodos anteriores. O registro de pagamento não comprova repasse bancário ao produtor. |
| RN10 | Sem fornecedor apto ou dados suficientes, apresentar o motivo e manter a pendência para decisão do funcionário. Alternativas não podem substituir silenciosamente os itens solicitados. O funcionário pode encerrar a solicitação sem atendimento. |
| RN11 | Notificações devem distinguir consulta de disponibilidade de alocação confirmada nos registros consultados. Uma sugestão não pode ser comunicada como compromisso de fornecimento. |

Nas consultas sem uma data informada, usar a data de recebimento e explicitá-la na resposta. A ausência de registros deve ser apresentada como informação não encontrada, sem concluir que o fato nunca ocorreu. As restrições sanitárias e documentais adotadas pertencem ao cenário simulado.

## Requisitos não funcionais

| ID | Requisito e verificação |
| --- | --- |
| RNF01 | Preservar mensagens, conversas e análises após fechar e reabrir a aplicação. Verificar que a retomada mantém os dados e separa o contexto de cada solicitação. |
| RNF02 | Indicar processamento em andamento. Após 60 segundos sem conclusão, informar a demora e permitir nova tentativa, preservando a solicitação. Verificar também o tratamento de falha do modelo ou das consultas. |
| RNF03 | Evitar duplicação de solicitações em novas tentativas da mesma operação. Uma alteração rejeitada deve preservar o registro anterior. Resultados de tentativas anteriores não podem sobrescrever análises ou esclarecimentos mais recentes. |
| RNF04 | Executar cálculos financeiros sobre os registros selecionados e conferir os resultados com valores esperados. A redação pelo modelo deve preservar esses resultados. |
| RNF05 | Proteger consultas e operações internas com validação de tokens JWT, rejeitando acessos sem token válido. |
| RNF06 | Disponibilizar os dados e documentos fornecidos por uma preparação inicial reproduzível, preservando originais, identificadores e fontes. Repetir a carga não deve duplicar registros nem preencher lacunas com dados fictícios adicionais. |

## Validação da entrega

Verificar as 15 mensagens fornecidas e consultas das três frentes com resultados esperados definidos antes dos testes. Conferir extração, classificação, perguntas de esclarecimento, fontes e reconhecimento de informação ausente ou conflitante.

Executar os fluxos com um funcionário e a base completa. Medir os tempos de análise e consulta e registrar as condições da demonstração. O limite de espera do RNF02 não representa garantia de conclusão nesse prazo.

## Expansões a decidir com a equipe

As funcionalidades abaixo dependem da aprovação da equipe e ficam fora do escopo atual. O registro, a alteração e a retirada de alocações dependem da decisão sobre os CRUDs.

1. Vamos implementar integrações com WhatsApp e e-mail? Se sim, vamos adotar um padrão de projeto que permita acrescentar integrações com outros softwares no futuro?
2. Se implementarmos as integrações, vamos permitir que o agente envie respostas aos remetentes e notificações aos produtores por WhatsApp e e-mail, após revisão do funcionário?
3. Vamos adicionar ao escopo do projeto CRUDs que ajudem o funcionário a gerenciar entidades do sistema, como produtores, produtos e documentos?
4. Se adicionarmos os CRUDs, vamos incluir um CRUD de pedidos com funcionalidade de agendamento para demandas como "Quero 20 tomates toda terça no meu restaurante"?

## Fora do escopo

- Acesso direto de produtores, compradores e auditores à plataforma.
- Alocações automáticas, controle de estoque e reservas, negociação comercial, acompanhamento de entregas e gestão de pagamentos.
