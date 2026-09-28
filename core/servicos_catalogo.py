"""Campos para preparar uma mensagem de contato; não criam atendimentos."""


def campo(nome, titulo, tipo="text", obrigatorio=False, opcoes=(), limite=100, dica=""):
    return {"nome": nome, "titulo": titulo, "tipo": tipo, "obrigatorio": obrigatorio,
            "opcoes": opcoes, "limite": limite, "dica": dica}


def servico(slug, titulo, grupo, descricao, campos):
    return {"slug": slug, "titulo": titulo, "grupo": grupo, "descricao": descricao,
            "campos": [campo("nome", "Seu nome", obrigatorio=True, limite=80), *campos,
                       campo("prazo", "Prazo ou disponibilidade", limite=100, dica="Opcional. Informe se há alguma data importante.")]}


def equipamento():
    return [campo("equipamento", "Tipo de equipamento", "select", True, ("Computador", "Notebook")),
            campo("modelo", "Marca e modelo", dica="Opcional. Preencha se souber.")]


def logistica():
    return [campo("local", "Cidade e bairro", dica="Opcional. Não é necessário informar o endereço completo."),
            campo("logistica", "Coleta e entrega", "select", False,
                  ("Quero combinar coleta e entrega", "Posso combinar a entrega do equipamento", "Ainda vou definir"))]


SERVICOS = [
    servico("formatacao", "Formatação", "Computadores e notebooks", "Conte sobre o equipamento e os cuidados necessários com seus arquivos.", [
        *equipamento(), campo("sistema", "Sistema atual ou desejado", dica="Opcional. Por exemplo, a versão do Windows."),
        campo("backup", "Precisa preservar arquivos?", "select", True,
              ("Sim, preciso de backup", "Já tenho backup", "Não preciso preservar arquivos", "Preciso de orientação")),
        campo("detalhes", "Motivo da formatação e programas necessários", "textarea", True, limite=450), *logistica()]),
    servico("limpeza", "Limpeza", "Computadores e notebooks", "Informe os sinais percebidos para orientar a avaliação da limpeza.", [
        *equipamento(), campo("sintomas", "O que você percebe no equipamento?", "textarea", True, limite=450,
              dica="Por exemplo: poeira, aquecimento, ruído ou manutenção preventiva."),
        campo("ultima_limpeza", "Quando foi a última limpeza?", dica="Opcional. Se não souber, pode deixar em branco."), *logistica()]),
    servico("conserto", "Conserto", "Computadores e notebooks", "Descreva o problema e quando ele começou. O diagnóstico será feito na avaliação.", [
        *equipamento(), campo("problema", "Qual é o problema?", "textarea", True, limite=450),
        campo("inicio", "Quando começou?"),
        campo("liga", "O equipamento liga?", "select", True, ("Sim", "Não", "Liga, mas não inicia o sistema", "Funciona de forma intermitente", "Não sei informar")), *logistica()]),
    servico("troca-pecas", "Troca de Peças", "Computadores e notebooks", "Informe a peça ou a melhoria desejada para verificarmos a compatibilidade.", [
        *equipamento(), campo("peca", "Peça ou melhoria desejada", obrigatorio=True, dica="Ex.: mais memória, SSD ou teclado. Se não souber, descreva o objetivo."),
        campo("possui_peca", "Você já possui a peça?", "select", True, ("Sim", "Não", "Preciso de orientação para comprar")),
        campo("objetivo", "O que deseja melhorar ou resolver?", "textarea", False, limite=350), *logistica()]),
    servico("outros-equipamentos", "Outros", "Computadores e notebooks", "Conte o que precisa em relação ao seu computador ou notebook.", [
        *equipamento(), campo("necessidade", "Como posso ajudar?", "textarea", True, limite=450), *logistica()]),
    servico("orcamentos-compra", "Orçamentos de Compra", "Serviços Digitais", "Informe o que pretende comprar e como será utilizado para orientar a pesquisa.", [
        campo("produto", "O que pretende comprar?", obrigatorio=True),
        campo("uso", "Finalidade e necessidades", "textarea", True, limite=450),
        campo("orcamento", "Faixa de orçamento", dica="Opcional. Informe uma estimativa em reais."),
        campo("preferencias", "Preferências ou requisitos", dica="Opcional. Ex.: marca, portabilidade ou programas que precisa utilizar.")]),
    servico("instalacao-sistemas", "Instalação e Programação de Sistemas", "Serviços Digitais", "Descreva o sistema e o que precisa instalar, configurar ou desenvolver.", [
        campo("sistema", "Nome ou tipo de sistema", obrigatorio=True),
        campo("atividade", "O que precisa fazer?", "select", True, ("Instalação", "Configuração", "Programação ou personalização", "Preciso de orientação")),
        campo("ambiente", "Onde será utilizado?", dica="Opcional. Ex.: computador, servidor ou aplicação web."),
        campo("necessidade", "Resultado esperado", "textarea", True, limite=450)]),
    servico("integracao-erp", "Integração de ERP com E-commerce", "Serviços Digitais", "Informe os sistemas envolvidos e os dados que precisam ser integrados.", [
        campo("erp", "Qual ERP utiliza?", obrigatorio=True),
        campo("loja", "Plataforma de e-commerce", obrigatorio=True, dica="Se ainda não escolheu a plataforma, informe isso aqui."),
        campo("dados", "Quais dados precisa integrar?", "textarea", True, limite=450,
              dica="Por exemplo: produtos, estoque, preços, pedidos ou notas fiscais."),
        campo("situacao", "Situação atual", "select", False, ("Nova integração", "Integração existente com problemas", "Melhoria de uma integração", "Ainda estou planejando"))]),
    servico("outros-digitais", "Outros", "Serviços Digitais", "Descreva o serviço digital e o resultado que você procura.", [
        campo("necessidade", "O que você precisa?", "textarea", True, limite=450),
        campo("ferramentas", "Sistemas ou ferramentas envolvidos", dica="Opcional."),
        campo("contexto", "Como funciona hoje?", "textarea", False, limite=300)]),
]


CONTATO = {
    "slug": "contato", "titulo": "Prepare sua mensagem", "grupo": "Contato", "modo": "contato",
    "descricao": "Conte o que você precisa e escolha por onde continuar a conversa.",
    "campos": [
        campo("nome", "Seu nome", obrigatorio=True, limite=80),
        campo("assunto", "Assunto", "select", True,
              ("Desenvolvimento de um projeto", "Serviço digital", "Manutenção de computador ou notebook",
               "Oportunidade profissional", "Outro assunto")),
        campo("mensagem", "O que você precisa?", "textarea", True, limite=1200),
        campo("prazo", "Prazo ou disponibilidade", limite=100, dica="Opcional. Informe se há alguma data importante."),
    ],
}
