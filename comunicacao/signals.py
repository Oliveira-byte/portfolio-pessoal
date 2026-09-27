from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from clientes.models import AtualizacaoSolicitacao, MensagemSolicitacao, ArquivoSolicitacao
from .services import notificar_evento


@receiver(pre_save, sender=AtualizacaoSolicitacao)
@receiver(pre_save, sender=ArquivoSolicitacao)
def visibilidade_anterior(sender, instance, raw=False, **kwargs):
    instance._liberado_agora = False
    if not raw and instance.pk and instance.visivel_cliente:
        instance._liberado_agora = sender.objects.filter(pk=instance.pk, visivel_cliente=False).exists()


@receiver(post_save, sender=AtualizacaoSolicitacao)
@receiver(post_save, sender=MensagemSolicitacao)
@receiver(post_save, sender=ArquivoSolicitacao)
def novidades(sender, instance, created, raw=False, **kwargs):
    if raw or not (created or getattr(instance, "_liberado_agora", False)):
        return
    tipo = {AtualizacaoSolicitacao: "atualizacao", MensagemSolicitacao: "mensagem", ArquivoSolicitacao: "arquivo"}[sender]
    notificar_evento(instance, tipo)
