window.prototypeSeed = {
    authenticated: false,
    view: "triage",
    triage: [
      { id: "PED-2026-003", state: "Recebida", buyer: "Mercado Bom Preço", type: "Pedido de compra", channel: "E-mail", urgent: "Urgente", urgencyReason: "Entrega solicitada para 29/10/2026, dia seguinte ao recebimento.", receivedAt: "2026-10-28T11:05:00-03:00", due: "29/10/2026", summary: "200 kg de tomate, entrega no centro de distribuição.", pending: "Prazo solicitado já venceu; confirmar nova data.", sample: true, source: "PED-2026-003", origin: "pedido", analysis: "Pedido identificado. O prazo 29/10/2026 foi preservado e está vencido na data de consulta.", original: "Olá, preciso de 200 kg de tomate para entregar no CD em 29/10. Conseguem atender?", drafts: ["pedido", "resposta"] },
      { id: "PED-2026-004", state: "Em análise", buyer: "Empório Raízes", type: "Pedido de compra", channel: "WhatsApp", urgent: "Normal", due: "20/11/2026", dueEnd: "24/11/2026", summary: "15 potes de mel orgânico e 30 kg de banana.", pending: "Conferir a vigência do DAP ou CAF.", sample: true, source: "PED-2026-004", origin: "pedido", analysisDocumentId: "DOC-DEMO-RAIZES", analysis: "O comprador pediu certificação orgânica para o mel. O contrato de demonstração exige DAP ou CAF vigente. Confira a vigência antes de decidir sobre o atendimento.", original: "Bom dia! Conforme o contrato de demonstração do Empório Raízes, reservem 15 potes de mel orgânico e 30 kg de banana para entrega de 20/11/2026 a 24/11/2026, se tiverem certificado orgânico válido para o mel.", drafts: ["pedido", "resposta"] },
      { id: "PED-2026-011", state: "Em análise", buyer: "Green Basket Co.", type: "Pedido de compra", channel: "E-mail", urgent: "Normal", due: "28/11/2026", summary: "80 bunches of kale and 40 kg of cassava.", pending: "Confirmar unidade do kale e condição de fornecimento.", sample: true, source: "PED-2026-011", origin: "pedido", analysis: "Mensagem em inglês interpretada: pedido de 80 maços de couve e 40 kg de mandioca.", original: "We need 80 bunches of kale and 40 kg of cassava by November 28th.", drafts: ["pedido"] },
      { id: "PED-2026-009", state: "Em análise", buyer: "Restaurante Semente", type: "Cotação", channel: "E-mail", urgent: "Normal", due: "25/11/2026", summary: "Cotação de hortaliças para menu semanal.", pending: "Solicita documentos cadastrais; decidir o que compartilhar.", sample: true, source: "PED-2026-009", origin: "cotação", analysis: "Cotação identificada. O remetente pede dados bancários e documentos; o rascunho externo omite esses dados.", original: "Podem enviar a cotação e também os documentos cadastrais e dados bancários da cooperativa?", drafts: ["resposta"] },
      {
        id: "PED-2026-014", state: "Recebida", buyer: "ADAGRO", type: "Comunicado", channel: "E-mail",
        urgent: "Normal", receivedAt: "2026-10-30T13:30:00-03:00",
        deadline: { action: "Disponibilizar documentos", date: "2026-11-11" },
        urgencyReason: "Os documentos devem estar disponíveis em 11/11/2026, primeiro dia da inspeção e depois do dia seguinte ao recebimento.",
        summary: "Inspeção sanitária em 11 e 12 de novembro com solicitação de documentos.",
        pending: "Conferir a disponibilidade dos documentos solicitados para a inspeção.",
        sample: true, source: "PED-2026-014", origin: "comunicado",
        analysis: "A ADAGRO solicita acesso a cadastros, certificações, laudos, registros de rastreabilidade e contratos durante a inspeção.",
        original: "Informamos que será realizada inspeção sanitária nos dias 11 e 12 de novembro de 2026. Solicitamos que estejam disponíveis para consulta os documentos indicados na notificação. [Trecho adaptado para a demonstração.]"
      },
      {
        id: "PED-2026-015", state: "Recebida", buyer: "Cícero (Produtor P003)", type: "Oferta", channel: "WhatsApp",
        urgent: "Urgente", receivedAt: "2026-10-30T16:00:00-03:00",
        deadline: { action: "Responder", date: "2026-10-31" },
        urgencyReason: "Retorno solicitado para 31/10/2026, dia seguinte ao recebimento.",
        summary: "Oferta de 200 kg de queijo coalho e 30 kg de manteiga com pedido de retorno.",
        pending: "Verificar se há pedidos para o produtor na semana.",
        sample: true, source: "PED-2026-015", origin: "oferta",
        analysis: "O produtor oferece queijo coalho e manteiga, pergunta se há pedidos naquela semana e manifesta interesse em indicar um novo produtor para cadastro.",
        original: "Lúcia, to com 200kg de queijo coalho pronto e 30kg de manteiga. Tem pedido pra mim essa semana? Se não tiver vou vender na feira direto. Me avisa até amanhã. [Trecho da mensagem.]"
      },
      { id: "MSG-TESTE-01", state: "Finalizada", buyer: "Ana Teste • contato de teste", type: "Consulta documental", channel: "WhatsApp", urgent: "Normal", due: "-", summary: "Pergunta sobre rastreabilidade do lote LOT-2026-0094.", result: "Respondida com fonte documental.", sample: false, source: "LOT-2026-0094", origin: "consulta", analysis: "Lote localizado: 300 unidades de alface, produtor João da Serra.", original: "Qual a origem e a quantidade do lote LOT-2026-0094?", drafts: ["resposta"] },
      { id: "MSG-TESTE-02", state: "Em análise", buyer: "Contato de teste • envio incerto", type: "Consulta documental", channel: "WhatsApp", urgent: "Indeterminada", summary: "Cenário de teste com envio sem confirmação do canal.", sample: false, contact: "Contato de teste", origin: "consulta", analysis: "Neste exemplo, o canal não confirma o resultado do envio.", original: "Vocês podem confirmar a quantidade registrada no lote LOT-2026-0094?", simulateUncertainSend: true, drafts: ["resposta"] }
    ],
    conversations: [],
    orders: [
      { id: "PED-2026-012", buyer: "Mercado Bom Preço", due: "30/09/2026", status: "Ativo", source: "PED-2026-012", conditions: "Entrega no CD; conferência no recebimento.", items: [{ name: "Tomate", qty: 100, unit: "kg", condition: "padrão de maturação" }], allocations: [{ id: "AL-1", item: "Tomate", producer: "João da Serra", qty: 100, unit: "kg", confirmed: true }] },
      { id: "PED-2026-020", buyer: "Cesta Viva", due: "22/11/2026", status: "Ativo", source: "-", conditions: "Produtos higienizados e identificados.", items: [{ name: "Alface", qty: 300, unit: "unidades", condition: "fresca" }], allocations: [] }
    ],
    producers: [{ id: "PR-001", name: "João da Serra", city: "Caruaru - PE", status: "Ativo", contact: "teste.joao@sabordaterra.test", linked: true }, { id: "PR-002", name: "Sítio Boa Água", city: "Gravatá - PE", status: "Ativo", contact: "5511999990001", linked: true }, { id: "PR-003", name: "Produtor sem vínculo", city: "Bonito - PE", status: "Ativo", contact: "-", linked: false }, { id: "P015", name: "Geraldo Manoel Barbosa", city: "Lajedo - PE", status: "Inativo", contact: "-" }],
    products: [{ id: "PROD-001", name: "Tomate", unit: "kg", season: "ano todo", linked: true }, { id: "PROD-002", name: "Mel orgânico", unit: "potes", season: "setembro a dezembro", linked: true }, { id: "PROD-003", name: "Couve", unit: "maços", season: "ano todo", linked: false }],
    documents: [
      { id: "DOC-2026-010", name: "Certificação orgânica • João da Serra", kind: "Certificado", status: "Vigente até 31/12/2026", linked: true, content: "CERTIFICADO DE PRODUÇÃO ORGÂNICA\\nTitular: João da Serra\\nProdutos cobertos: mel orgânico\\nValidade: 01/01/2026 a 31/12/2026\\nRegistro: CERT-ORG-2026-44" },
      { id: "DOC-2026-011", name: "Rastreabilidade LOT-2026-0094", kind: "Lote", status: "Registrado", linked: true, content: "REGISTRO DE RASTREABILIDADE\\nLote: LOT-2026-0094\\nProduto: Alface\\nQuantidade: 300 unidades\\nOrigem: João da Serra\\nColheita: 08/11/2026" },
      { id: "DOC-IMPORT-01", name: "Documento importado sem vínculo", kind: "Anexo", status: "Disponível", linked: false, content: "Arquivo original usado na demonstração." },
      { id: "DOC-DEMO-RAIZES", name: "Contrato de demonstração do Empório Raízes", kind: "Contrato", status: "Disponível", content: "Para este fornecimento, os produtores devem apresentar DAP ou CAF vigente. Documento fictício usado no protótipo." },
      { id: "DOC-DEMO-CAPACIDADE", name: "Ficha de capacidade do João da Serra", kind: "Ficha técnica", status: "Disponível", content: "Capacidade estimada de tomate: 100 kg por semana. Estimativa fictícia usada no protótipo." }
    ],
    sends: []
  };
