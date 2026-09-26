from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
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
