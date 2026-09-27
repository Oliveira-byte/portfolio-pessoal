from django.conf import settings
from django.core.checks import Error, Warning, register
from .services import url_site, email_valido


@register()
def configuracao_email(app_configs, **kwargs):
    erros = []
    try:
        url_site("/")
    except Exception:
        erros.append(Error("SITE_URL deve conter somente a origem do site; use HTTPS em produção.", id="comunicacao.E001"))
    smtp = settings.MAILERS["default"]["BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"
    if settings.SMTP_USE_TLS and settings.SMTP_USE_SSL:
        erros.append(Error("Escolha TLS ou SSL, não os dois.", id="comunicacao.E002"))
    for nome in ("EMAIL_EQUIPE", "EMAIL_REPLY_TO"):
        valor = getattr(settings, nome)
        if valor and not email_valido(valor):
            erros.append(Error(f"{nome} deve ser um endereço de e-mail válido.", id="comunicacao.E003"))
    if smtp and (not settings.SMTP_HOST or not email_valido(settings.DEFAULT_FROM_EMAIL)):
        erros.append(Error("Configure EMAIL_HOST e DEFAULT_FROM_EMAIL para envio SMTP.", id="comunicacao.E004"))
    return erros


@register(deploy=True)
def email_producao(app_configs, **kwargs):
    avisos = []
    if settings.MAILERS["default"]["BACKEND"] != "django.core.mail.backends.smtp.EmailBackend":
        avisos.append(Warning("O e-mail está em modo de desenvolvimento. Configure SMTP antes da publicação.", id="comunicacao.W001"))
    if not settings.SITE_URL.startswith("https://"):
        avisos.append(Warning("Configure SITE_URL com o domínio HTTPS antes da publicação.", id="comunicacao.W002"))
    return avisos
