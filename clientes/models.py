from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .storage import caminho_arquivo, private_storage, validar_arquivo


class SolicitacaoQuerySet(models.QuerySet):
    def para_cliente(self, usuario):
        if not usuario.is_authenticated:
            return self.none()
        return self.filter(cliente=usuario, visivel_cliente=True)


class Solicitacao(models.Model):
    class Tipo(models.TextChoices):
        PROJETO = "projeto", "Projeto"
        SERVICO = "servico", "Serviço"
        MANUTENCAO = "manutencao", "Manutenção técnica"

    class Status(models.TextChoices):
        RECEBIDA = "recebida", "Recebida"
        PLANEJAMENTO = "planejamento", "Em planejamento"
        ANDAMENTO = "andamento", "Em andamento"
        AGUARDANDO = "aguardando_cliente", "Aguardando você"
        PAUSADA = "pausada", "Pausada"
        CONCLUIDA = "concluida", "Concluída"
        CANCELADA = "cancelada", "Cancelada"

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="solicitacoes", verbose_name="cliente",
    )
    titulo = models.CharField("título", max_length=160)
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices, default=Tipo.PROJETO)
    descricao = models.TextField("escopo contratado")
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.RECEBIDA)
    progresso = models.PositiveSmallIntegerField(
        "progresso (%)", default=0, validators=[MaxValueValidator(100)],
        help_text="Percentual informado por você. Ao concluir pelo admin, será ajustado para 100%.",
    )
    proximo_passo = models.TextField(
        "próximo passo", blank=True,
        help_text="Explique a próxima entrega ou o que precisa receber do cliente.",
    )
    data_inicio = models.DateField("data de início", blank=True, null=True)
    prazo = models.DateField("previsão de entrega", blank=True, null=True)
    visivel_cliente = models.BooleanField(
        "visível para o cliente", default=False,
        help_text="Marque para liberar a contratação e seu histórico no painel do cliente.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    objects = SolicitacaoQuerySet.as_manager()

    class Meta:
        verbose_name = "projeto ou serviço contratado"
        verbose_name_plural = "projetos e serviços contratados"
        ordering = ("-atualizado_em", "-pk")
        indexes = [models.Index(fields=["cliente", "visivel_cliente", "status"], name="sol_cliente_vis_status")]
        constraints = [
            models.CheckConstraint(condition=Q(progresso__gte=0, progresso__lte=100), name="sol_progresso_0_100"),
            models.CheckConstraint(condition=~Q(status="concluida") | Q(progresso=100), name="sol_concluida_100"),
            models.CheckConstraint(condition=Q(prazo__isnull=True) | Q(data_inicio__isnull=True) | Q(prazo__gte=models.F("data_inicio")), name="sol_prazo_apos_inicio"),
        ]

    def clean(self):
        super().clean()
        if self.status == self.Status.CONCLUIDA:
            self.progresso = 100
        if self.prazo and self.data_inicio and self.prazo < self.data_inicio:
            raise ValidationError({"prazo": "A previsão de entrega não pode ser anterior ao início."})
        if self.status == self.Status.AGUARDANDO and not self.proximo_passo.strip():
            raise ValidationError({"proximo_passo": "Informe o que precisa receber do cliente."})

    @property
    def eh_manutencao(self):
        return self.tipo == self.Tipo.MANUTENCAO

    @property
    def manutencao(self):
        if isinstance(self, OrdemManutencao):
            return self
        return getattr(self, "ordemmanutencao", None) if self.eh_manutencao else None

    @property
    def status_publico(self):
        return self.manutencao.get_etapa_display() if self.manutencao else self.get_status_display()

    @property
    def referencia(self):
        return f"OS #{self.pk}" if self.eh_manutencao else f"Solicitação #{self.pk}"

    @property
    def encerrada(self):
        return self.status in (self.Status.CONCLUIDA, self.Status.CANCELADA)

    @property
    def prazo_vencido(self):
        return bool(self.prazo and self.prazo < timezone.localdate() and not self.encerrada)

    def get_absolute_url(self):
        return reverse("area_cliente:solicitacao_detalhe", kwargs={"pk": self.pk})

    def __str__(self):
        return f"{self.titulo} — {self.cliente}"


class AtualizacaoSolicitacao(models.Model):
    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE, related_name="atualizacoes", verbose_name="contratação")
    titulo = models.CharField("título", max_length=160)
    mensagem = models.TextField("mensagem", blank=True)
    visivel_cliente = models.BooleanField("visível para o cliente", default=True)
    status_registrado = models.CharField("status no registro", max_length=20, choices=Solicitacao.Status.choices, blank=True)
    progresso_registrado = models.PositiveSmallIntegerField("progresso no registro", null=True, blank=True, validators=[MaxValueValidator(100)])
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="atualizacoes_registradas")
    criado_em = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "atualização da contratação"
        verbose_name_plural = "atualizações das contratações"
        ordering = ("-criado_em", "-pk")

    def __str__(self):
        return self.titulo


class Origem(models.TextChoices):
    CLIENTE = "cliente", "Cliente"
    EQUIPE = "equipe", "Atendimento"


class ArquivoSolicitacao(models.Model):
    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE, related_name="arquivos", verbose_name="contratação")
    titulo = models.CharField("título do arquivo", max_length=160)
    arquivo = models.FileField("arquivo", upload_to=caminho_arquivo, storage=private_storage, validators=[validar_arquivo], max_length=255)
    nome_original = models.CharField("nome original", max_length=255, editable=False)
    tamanho = models.PositiveBigIntegerField("tamanho em bytes", editable=False, default=0)
    origem = models.CharField("enviado por", max_length=10, choices=Origem.choices, default=Origem.EQUIPE, editable=False)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False, related_name="arquivos_enviados")
    visivel_cliente = models.BooleanField("visível para o cliente", default=True)
    criado_em = models.DateTimeField("enviado em", auto_now_add=True)

    class Meta:
        verbose_name = "arquivo da contratação"
        verbose_name_plural = "arquivos das contratações"
        ordering = ("-criado_em", "-pk")

    def save(self, *args, **kwargs):
        from .storage import nome_seguro
        if self.pk:
            anterior = type(self).objects.get(pk=self.pk)
            if anterior.arquivo.name != self.arquivo.name or not self.arquivo._committed or anterior.solicitacao_id != self.solicitacao_id:
                raise ValidationError("Envie um novo registro para substituir ou mover um arquivo.")
        if not self.arquivo._committed:
            validar_arquivo(self.arquivo)
            self.nome_original = nome_seguro(self.arquivo.name)
            self.tamanho = self.arquivo.size
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo


class MensagemSolicitacao(models.Model):
    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE, related_name="mensagens", verbose_name="contratação")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False, related_name="mensagens_enviadas")
    origem = models.CharField("enviada por", max_length=10, choices=Origem.choices, default=Origem.EQUIPE, editable=False)
    texto = models.TextField("mensagem", max_length=5000)
    criado_em = models.DateTimeField("enviada em", auto_now_add=True)
    lida_cliente_em = models.DateTimeField("lida pelo cliente em", null=True, blank=True, editable=False)
    lida_equipe_em = models.DateTimeField("lida pela equipe em", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "mensagem da contratação"
        verbose_name_plural = "mensagens das contratações"
        ordering = ("-criado_em", "-pk")
        indexes = [models.Index(fields=["solicitacao", "origem", "lida_cliente_em"], name="msg_cliente_leitura"), models.Index(fields=["origem", "lida_equipe_em"], name="msg_equipe_leitura")]

    def __str__(self):
        return f"{self.get_origem_display()} · {self.solicitacao.titulo}"


class OrdemManutencao(Solicitacao):
    class Equipamento(models.TextChoices):
        COMPUTADOR = "computador", "Computador"
        NOTEBOOK = "notebook", "Notebook"

    class Etapa(models.TextChoices):
        AGENDADO = "agendado", "Recebimento agendado"
        RECEBIDO = "recebido", "Equipamento recebido"
        DIAGNOSTICO = "diagnostico", "Em diagnóstico"
        ORCAMENTO = "orcamento", "Orçamento em negociação"
        PECA = "aguardando_peca", "Aguardando peça"
        MANUTENCAO = "manutencao", "Em manutenção"
        TESTES = "testes", "Em testes"
        PRONTO = "pronto", "Pronto para entrega ou retirada"
        ENTREGUE = "entregue", "Entregue"
        CANCELADO = "cancelado", "Cancelado"

    equipamento = models.CharField("equipamento", max_length=12, choices=Equipamento.choices)
    marca = models.CharField("marca", max_length=80)
    modelo = models.CharField("modelo", max_length=120)
    numero_serie = models.CharField("número de série", max_length=120, blank=True)
    relato_cliente = models.TextField("problema relatado pelo cliente")
    acessorios = models.TextField("acessórios recebidos", blank=True)
    condicao_recebimento = models.TextField("condição do equipamento no recebimento", blank=True)
    diagnostico_publico = models.TextField("diagnóstico visível ao cliente", blank=True)
    servico_realizado = models.TextField("serviço realizado / orientação ao cliente", blank=True)
    anotacoes_internas = models.TextField("anotações técnicas internas", blank=True, help_text="Somente na administração. Não registre senhas de acesso do equipamento.")
    etapa = models.CharField("etapa da manutenção", max_length=20, choices=Etapa.choices, default=Etapa.AGENDADO)
    orcamento_acordado = models.BooleanField("orçamento já acordado com o cliente", default=False, help_text="Marque somente após combinar os valores pelo contato. O cliente consultará o registro, sem aprovar pelo site.")
    detalhes_orcamento = models.TextField("descrição do que foi acordado", blank=True)
    valor_servicos = models.DecimalField("serviços (R$)", max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    valor_pecas = models.DecimalField("peças (R$)", max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    valor_logistica = models.DecimalField("coleta e entrega (R$)", max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    data_acordo = models.DateField("data do acordo", null=True, blank=True)
    pagamento_combinado = models.CharField("condição de pagamento combinada", max_length=200, blank=True)
    recebimento = models.CharField("forma de recebimento", max_length=10, choices=[("coleta", "Coleta por Danilo"), ("cliente", "Entrega pelo cliente")], default="coleta")
    coleta_prevista = models.DateTimeField("recebimento / coleta agendada", null=True, blank=True)
    recebido_em = models.DateField("recebido em", null=True, blank=True)
    devolucao = models.CharField("forma de devolução", max_length=10, choices=[("entrega", "Entrega por Danilo"), ("retirada", "Retirada pelo cliente")], default="entrega")
    devolucao_prevista = models.DateTimeField("entrega / retirada agendada", null=True, blank=True)
    entregue_em = models.DateField("entregue em", null=True, blank=True)
    endereco_atendimento = models.TextField("endereço combinado para coleta / entrega", blank=True, help_text="Visível somente nesta ordem, ao cliente titular e à administração.")
    observacoes_logistica = models.TextField("orientações de coleta / entrega", blank=True)

    class Meta:
        verbose_name = "ordem de manutenção técnica"
        verbose_name_plural = "manutenção técnica — ordens de serviço"
        ordering = ("-atualizado_em", "-pk")
        constraints = [
            models.CheckConstraint(condition=Q(valor_servicos__isnull=True) | Q(valor_servicos__gte=0), name="os_servicos_positivo"),
            models.CheckConstraint(condition=Q(valor_pecas__gte=0) & Q(valor_logistica__gte=0), name="os_custos_positivos"),
            models.CheckConstraint(condition=~Q(orcamento_acordado=True) | (Q(valor_servicos__isnull=False) & Q(data_acordo__isnull=False)), name="os_acordo_com_valor_data"),
            models.CheckConstraint(condition=Q(entregue_em__isnull=True) | Q(recebido_em__isnull=True) | Q(entregue_em__gte=models.F("recebido_em")), name="os_entrega_apos_recebimento"),
        ]

    def sincronizar_acompanhamento(self):
        self.tipo = self.Tipo.MANUTENCAO
        self.status = {
            self.Etapa.AGENDADO: self.Status.RECEBIDA,
            self.Etapa.RECEBIDO: self.Status.RECEBIDA,
            self.Etapa.ORCAMENTO: self.Status.PLANEJAMENTO,
            self.Etapa.PECA: self.Status.PAUSADA,
            self.Etapa.ENTREGUE: self.Status.CONCLUIDA,
            self.Etapa.CANCELADO: self.Status.CANCELADA,
        }.get(self.etapa, self.Status.ANDAMENTO)
        self.progresso = 100 if self.etapa == self.Etapa.ENTREGUE else 0

    def clean(self):
        self.sincronizar_acompanhamento()
        super().clean()
        erros = {}
        if self.orcamento_acordado:
            if self.valor_servicos is None:
                erros["valor_servicos"] = "Informe o valor dos serviços; use zero quando não houver cobrança."
            if not self.data_acordo:
                erros["data_acordo"] = "Informe quando o orçamento foi acordado."
            if not self.detalhes_orcamento.strip():
                erros["detalhes_orcamento"] = "Descreva os serviços e valores combinados."
        if self.entregue_em and self.recebido_em and self.entregue_em < self.recebido_em:
            erros["entregue_em"] = "A entrega não pode ser anterior ao recebimento."
        if self.etapa == self.Etapa.ENTREGUE and (not self.recebido_em or not self.entregue_em):
            erros["entregue_em"] = "Para encerrar como entregue, registre as datas de recebimento e entrega."
        if self.coleta_prevista and self.devolucao_prevista and self.devolucao_prevista < self.coleta_prevista:
            erros["devolucao_prevista"] = "A devolução prevista não pode ser anterior à coleta."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.sincronizar_acompanhamento()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"tipo", "status", "progresso"}
        super().save(*args, **kwargs)

    @property
    def total_acordado(self):
        if not self.orcamento_acordado:
            return None
        return sum((self.valor_servicos or Decimal("0"), self.valor_pecas, self.valor_logistica), Decimal("0"))
