from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class ConfiguracaoContato(models.Model):
    email = models.EmailField("e-mail de atendimento", default="danilooliv.m@hotmail.com")
    whatsapp = models.CharField("número do WhatsApp Business", max_length=15, blank=True, validators=[RegexValidator(r"^[0-9]{10,15}$", "Use somente números, incluindo país e DDD.")], help_text="Somente números, incluindo país e DDD. Deixe vazio enquanto o número não estiver definido.")
    whatsapp_ativo = models.BooleanField("exibir WhatsApp no site", default=False)

    class Meta:
        verbose_name = "configuração de contato"
        verbose_name_plural = "configuração de contato"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="contato_registro_unico")]

    def clean(self):
        super().clean()
        if self.whatsapp_ativo and not self.whatsapp:
            raise ValidationError({"whatsapp": "Informe o número antes de ativar o WhatsApp."})

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def whatsapp_url(self):
        return f"https://wa.me/{self.whatsapp}" if self.whatsapp_ativo and self.whatsapp else ""

    def __str__(self):
        return "Canais de atendimento"
