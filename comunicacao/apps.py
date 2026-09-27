from django.apps import AppConfig


class ComunicacaoConfig(AppConfig):
    name = "comunicacao"
    verbose_name = "E-mails do atendimento"

    def ready(self):
        from . import checks, signals  # noqa: F401
