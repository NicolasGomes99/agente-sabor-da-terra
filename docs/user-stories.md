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

Requisitos: RF02, RF03, RF04, RF11, RF12; RN07, RN08.

Critérios de aceitação:

- A entrada preserva identificador, mensagem original, remetente, canal e data de recebimento.
- O cartão apresenta o resumo, o tipo, a urgência justificada e as pendências. Sua expansão abre a conversa iniciada pela análise do agente e permite conferir a mensagem original.
- A análise organiza os dados extraídos e preserva condições como "se tiver", a frequência de fornecimento e intenções adicionais, como uma oferta acompanhada de solicitação de cadastro.

## US03 - Esclarecer ambiguidades

Como funcionário, quero discutir os pontos incertos com o assistente para completar a análise sem adivinhar a intenção do remetente.

Requisitos: RF01, RF07, RF10, RF13; RN03, RN06.

Critérios de aceitação:

- Produto indefinido, quantidade agregada ou data conflitante gera uma pergunta específica, preservando as informações já compreendidas.
- O assistente registra o esclarecimento na conversa e atualiza a análise, a sugestão e os alertas afetados, preservando a mensagem original.
- Perguntas de acompanhamento usam o contexto daquela conversa, sem incorporar dados de outra solicitação.

## US04 - Avaliar uma sugestão de atendimento

Como funcionário, quero conhecer os produtores candidatos para comparar alternativas de atendimento.

Requisitos: RF14; RN01 a RN04, RN10.

Critérios de aceitação:

- A sugestão identifica candidatos, fontes, quantidades justificáveis e disponibilidade ainda não confirmada.
- Produtores inaptos são excluídos da sugestão para aquele atendimento, com indicação do motivo. Dados ausentes ou conflitantes aparecem como pendências.
- O funcionário pode discutir alternativas no chat. Alterar a sugestão não registra uma alocação.

## US05 - Acompanhar a triagem

Como funcionário, quero consultar a situação das solicitações para identificar o que ainda depende de decisão.

Requisitos: RF12, RF15; RN10.

Critérios de aceitação:

- A solicitação apresenta um dos estados definidos no RF15 e as pendências existentes.
- Sem fornecedor apto, a análise explica o motivo. O funcionário pode buscar esclarecimentos ou encerrar sem atendimento.
- O encerramento registra o resultado da triagem e as pendências restantes.

## US06 - Consultar documentos e dados

Como funcionário, quero fazer perguntas sobre os registros da cooperativa para responder às demandas com fontes verificáveis.

Requisitos: RF01, RF05, RF06, RF07, RF17; RN01, RN05; RNF06.

Critérios de aceitação:

- A consulta pode combinar documentos e dados operacionais na mesma conversa.
- A resposta identifica documentos e registros ou trechos que sustentam as afirmações. Consultas sobre certificação verificam validade e produto coberto; consultas sobre lote identificam sua origem registrada.
- Preços informam vigência e condições. Informação ausente ou conflitante é explicitada, sem completar a resposta por suposição.
- A referência a um documento permite abri-lo para leitura completa na plataforma e baixar o arquivo original.

## US07 - Consultar e baixar o resumo de um produtor

Como funcionário, quero gerar e baixar em PDF um resumo por produtor para informar suas vendas, pedidos alocados e pendências financeiras.

Requisitos: RF08, RF18; RN03, RN09; RNF04.

Critérios de aceitação:

- O resumo identifica produtor, período e data de referência, com fontes dos valores e registros apresentados.
- Vendas do período e pagamentos registrados aparecem separados das pendências vencidas e a vencer, inclusive quando originadas em períodos anteriores. Quantidades respeitam produto e unidade.
- Pedidos alocados são apresentados apenas quando houver registros que comprovem a alocação na base consultada. Sugestões não são incluídas como alocações.
- Ausência de registro é informada como tal; pagamento registrado não é apresentado como comprovação de repasse bancário.
- O resumo é acompanhado da opção "Baixar resumo em PDF". O arquivo preserva o conteúdo e as fontes exibidos.

## US08 - Preparar uma notificação

Como funcionário, quero solicitar uma notificação para um produtor para comunicar uma demanda com clareza.

Requisitos: RF09; RN11.

Critérios de aceitação:

- O texto identifica o produtor, os produtos, as quantidades e os prazos conhecidos, indicando o que ainda precisa de confirmação.
- Uma consulta de disponibilidade é distinta de uma comunicação de alocação confirmada nos registros consultados.
- A notificação fica disponível para revisão e cópia pelo funcionário, sem envio automático.

## US09 - Retomar o trabalho

Como funcionário, quero reencontrar as solicitações e suas conversas para continuar a triagem após sair da aplicação.

Requisitos: RF10; RNF01.

Critérios de aceitação:

- Após reabrir a aplicação e se autenticar, o funcionário encontra mensagens, análises e conversas preservadas.
- Ao retomar uma conversa, o assistente considera seus esclarecimentos anteriores e mantém o contexto separado das demais solicitações.

## US10 - Recuperar uma operação com falha

Como funcionário, quero saber quando uma operação falhou e poder tentar novamente para continuar o atendimento.

Requisitos: RNF02, RNF03.

Critérios de aceitação:

- A interface indica processamento e informa falhas. Sem conclusão após 60 segundos, informa a demora e oferece nova tentativa.
- A solicitação permanece disponível. Uma nova tentativa não duplica registros; uma alteração rejeitada mantém o registro anterior.
- Uma resposta atrasada de uma tentativa anterior não substitui análises ou esclarecimentos mais recentes.
