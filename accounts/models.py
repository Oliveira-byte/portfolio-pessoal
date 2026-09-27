import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Modelo de usuário personalizado do projeto.

    Inicialmente utiliza os campos padrão do Django,
    permitindo futuras expansões sem precisarmos
    substituir o modelo de usuário depois.
    """

    acesso_pendente = models.BooleanField("aguardando definição da senha", default=False, editable=False)
    versao_acesso = models.UUIDField(default=uuid.uuid4, editable=False)

    def save(self, *args, **kwargs):
        campos = kwargs.get("update_fields")
        if self.pk and (campos is None or set(campos) & {"password", "email", "is_active"}):
            anterior = type(self).objects.filter(pk=self.pk).values("password", "email", "is_active").first()
            if anterior and any(anterior[c] != getattr(self, c) for c in anterior if campos is None or c in campos):
                self.versao_acesso = uuid.uuid4()
                if campos is not None:
                    kwargs["update_fields"] = set(campos) | {"versao_acesso"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username