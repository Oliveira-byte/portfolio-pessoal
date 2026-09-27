from django.conf import settings
from django.db import models


class EntregaEmail(models.Model):
    class Tipo(models.TextChoices):
        ACESSO = "acesso", "Convite de acesso"
        SENHA = "senha", "Recuperação de senha"
        ATUALIZACAO = "atualizacao", "Atualização do atendimento"
        MENSAGEM = "mensagem", "Nova mensagem"
        ARQUIVO = "arquivo", "Novo arquivo"

    class Estado(models.TextChoices):
        PENDENTE = "pendente", "Aguardando envio"
        ENVIANDO = "enviando", "Em envio"
        ENVIADO = "enviado", "Aceito pelo servidor de e-mail"
        SIMULADO = "simulado", "Simulado — sem envio real"
        FALHA = "falha", "Falha no envio"
        CANCELADO = "cancelado", "Envio cancelado"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDENTE, db_index=True)
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="entregas_email")
    destinatario = models.EmailField()
    para_equipe = models.BooleanField(default=False)
    solicitacao = models.ForeignKey("clientes.Solicitacao", null=True, blank=True, on_delete=models.SET_NULL)
    referencia_id = models.PositiveBigIntegerField(null=True, blank=True)
    # Identifica o evento; não armazena o conteúdo do e-mail, senha ou token de acesso.
    chave = models.CharField(max_length=120, unique=True)
    versao_acesso = models.UUIDField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    tentativas = models.PositiveIntegerField(default=0)
    resultado = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-criado_em", "-pk")
        verbose_name = "entrega de e-mail"
        verbose_name_plural = "entregas de e-mail"

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.get_estado_display()}"
