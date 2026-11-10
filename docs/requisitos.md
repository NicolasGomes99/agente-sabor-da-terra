## Requisitos
#### Situação do levantamento

Rascunho para discussão da equipe. Os requisitos extraídos do enunciado ainda precisam de critérios de aceitação detalhados. Regras observadas nos dados e propostas da equipe não devem ser confundidas com funcionalidades já aprovadas.

- **Fonte principal:** Projeto Intermediário - Formação Sauter.pdf, seções 4 e 5.
- **Material complementar:** arquivos simulados da Cooperativa Sabor da Terra.

#### Requisitos funcionais do enunciado

| ID | Requisito |
| --- | --- |
| RF01 | Permitir que a equipe da cooperativa interaja com o assistente por texto em uma interface conversacional. |
| RF02 | Interpretar mensagens em português coloquial, incluindo abreviações, erros de digitação e informações incompletas ou ambíguas. |
| RF03 | Extrair e organizar produtos, quantidades, prazos e dados do comprador presentes nos pedidos. |
| RF04 | Classificar pedidos e sinalizar urgências e problemas, incluindo produtos fora de safra e quantidades acima da capacidade documentada. |
| RF05 | Responder a consultas sobre certificações, rastreabilidade, sazonalidade e histórico de lotes utilizando os dados fornecidos. |
| RF06 | Identificar os documentos ou registros que fundamentam as respostas. |
| RF07 | Informar quando não encontrar informação suficiente para responder, sem apresentar suposições como fatos. |
| RF08 | Gerar, quando solicitado, resumos personalizados por produtor com vendas, pedidos alocados e pendências financeiras. |
| RF09 | Redigir, quando solicitado, notificações para produtores sobre novos pedidos de seus produtos. |
| RF10 | Manter o contexto da conversa ao longo de uma sessão. |

A redação de notificações não implica envio real. O enunciado não especifica o mecanismo de alocação nem autoriza presumir alocação automática.

#### Regras de negócio a formalizar

| ID | Regra candidata | Ponto a esclarecer |
| --- | --- | --- |
| RN01 | Verificar validade e escopo da certificação para afirmar que um produto é orgânico. | Data de referência, divergências e ausência de comprovação. |
| RN02 | Considerar situação cadastral e restrições sanitárias aplicáveis ao fornecimento. | Condições por produto, comprador e documentação disponível. |
| RN03 | Preservar unidades e converter apenas quando houver equivalência conhecida. | Tratamento de caixas, maços, unidades e dúzias. |
| RN04 | Distinguir sazonalidade, capacidade estimada e estoque disponível. | Informação necessária para confirmar atendimento ou reservar produtos. |
| RN05 | Aplicar preços conforme a fonte e as condições pertinentes ao pedido. | Precedência entre contrato, tabela e ficha técnica; limites de descontos. |
| RN06 | Interpretar datas relativas considerando a data de recebimento da mensagem. | Fuso horário, datas conflitantes e esclarecimentos ao usuário. |
| RN07 | Distinguir compras, cotações, consultas financeiras, ofertas de produtores e notificações oficiais. | Categorias, prioridade e encaminhamento de cada tipo. |

As restrições dos documentos pertencem ao cenário simulado; não representam validação da legislação vigente.

#### Funcionalidades propostas, pendentes de decisão

- **Navegação:** áreas de chat, pedidos e documentos, conforme proposta discutida.
- **Pedidos:** definir consulta, cadastro, edição, estados e aprovação de alocações.
- **Produtores e documentos:** definir se haverá cadastro, edição e envio de novos arquivos.
- **Acesso:** definir login, atores e permissões.
- **Histórico:** definir persistência entre sessões e documentos salvos por usuário.
- **Comunicação:** definir se notificações serão apenas rascunhos ou terão envio real.
- **Integrações:** definir se mensagens serão inseridas manualmente ou recebidas por canais externos.

#### Requisitos não funcionais a levantar

Os tópicos abaixo ainda não são requisitos aprovados; precisam de critérios mensuráveis e forma de verificação.

- **Desempenho:** tempo esperado de resposta para consultas e para o agente; comportamento durante a espera.
- **Capacidade:** volume de usuários simultâneos, mensagens e documentos esperado no protótipo.
- **Segurança e privacidade:** autenticação, permissões, proteção de dados cadastrais e financeiros e gestão de credenciais.
- **Confiabilidade:** tratamento de falhas do modelo, indisponibilidade de serviços e operações parcialmente concluídas.
- **Integridade:** precisão de cálculos, consistência das alterações e prevenção de registros duplicados.
- **Rastreabilidade:** fontes das respostas e registro de alterações e aprovações, conforme o escopo.
- **Usabilidade e acessibilidade:** clareza das pendências, erros e confirmações; condições de uso da interface.
- **Operação e custo:** orçamento, implantação, execução local, observabilidade, backup e recuperação.
- **Qualidade das respostas:** conjunto de avaliação e critérios para extração, fundamentação e reconhecimento de informação ausente.

#### User stories

Serão elaboradas após definir os atores e os fluxos prioritários, com critérios de aceitação verificáveis.

- **Formato:** Como [ator], quero [ação ou capacidade] para [benefício].
- **Critérios:** registrar condições de sucesso, exceções, ambiguidades e permissões aplicáveis.

#### Questões iniciais

1. Quem utilizará o protótipo: somente a equipe da cooperativa ou também produtores, compradores e auditores diretamente?
2. Como as mensagens entrarão no sistema: texto colado no chat, seleção dos pedidos fornecidos, formulário ou integração externa?
3. O sistema apenas analisará e proporá atendimento ou também persistirá pedidos e alocações aprovadas?

