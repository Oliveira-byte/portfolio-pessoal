from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import ArquivoSolicitacao


@receiver(post_delete, sender=ArquivoSolicitacao)
def remover_arquivo_privado(sender, instance, using, **kwargs):
    if instance.arquivo.name:
        storage, name = instance.arquivo.storage, instance.arquivo.name
        transaction.on_commit(lambda: storage.delete(name), using=using)
