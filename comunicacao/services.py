import logging
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.acesso import cliente_apto, email_exclusivo, token_acesso
from clientes.models import AtualizacaoSolicitacao, MensagemSolicitacao, ArquivoSolicitacao, Origem
from .models import EntregaEmail

logger = logging.getLogger(__name__)


def url_site(path):
    base = settings.SITE_URL.rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or (not settings.DEBUG and parsed.scheme != "https" and settings.MAILERS["default"]["BACKEND"] == "django.core.mail.backends.smtp.EmailBackend")):
        raise ImproperlyConfigured("Configure SITE_URL com a origem do site; em produção, use HTTPS.")
    return base + path


def email_valido(value):
    try:
        validate_email(value)
    except ValidationError:
        return False
    return True


def criar_entrega(**kwargs):
    registro, novo = EntregaEmail.objects.get_or_create(chave=kwargs.pop("chave"), defaults=kwargs)
    if novo and settings.EMAIL_ENVIO_IMEDIATO:
        transaction.on_commit(lambda: processar_entrega(registro.pk))
    return registro


def solicitar_acesso(user, *, renovar=False):
    if not cliente_apto(user) or not email_valido(user.email) or not email_exclusivo(user):
        raise ValidationError("Informe um e-mail exclusivo e válido para um cliente ativo, sem permissões administrativas.")
    if not user.has_usable_password() and not user.acesso_pendente:
        raise ValidationError("Esta conta não está habilitada para acesso por senha. Confira seu cadastro no admin.")
    with transaction.atomic():
        if renovar:
            user.versao_acesso = uuid.uuid4()
            user.save(update_fields=["versao_acesso"])
        return criar_entrega(
            tipo=EntregaEmail.Tipo.ACESSO if user.acesso_pendente else EntregaEmail.Tipo.SENHA,
            cliente=user, destinatario=user.email.strip(), versao_acesso=user.versao_acesso,
            chave="acesso:" + str(uuid.uuid4()),
        )


def notificar_evento(obj, tipo):
    if not settings.EMAIL_NOTIFICACOES_ATIVAS:
        return
    sol = obj.solicitacao
    if not sol.visivel_cliente or not getattr(obj, "visivel_cliente", True):
        return
    para_equipe = getattr(obj, "origem", None) == Origem.CLIENTE
    cliente = sol.cliente
    destino = settings.EMAIL_EQUIPE if para_equipe else cliente.email
    if not email_valido(destino) or not cliente_apto(cliente):
        return
    if not para_equipe and (cliente.acesso_pendente or not email_exclusivo(cliente)):
        return
    criar_entrega(tipo=tipo, cliente=cliente, destinatario=destino, para_equipe=para_equipe,
                  solicitacao=sol, referencia_id=obj.pk, chave=f"{tipo}:{obj.pk}")


def contexto_entrega(item):
    user = item.cliente
    if not cliente_apto(user):
        return None
    if item.tipo in (EntregaEmail.Tipo.ACESSO, EntregaEmail.Tipo.SENHA):
        if (item.versao_acesso != user.versao_acesso or item.destinatario.casefold() != user.email.strip().casefold()
                or not email_exclusivo(user) or item.criado_em < timezone.now() - timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
                or (item.tipo == EntregaEmail.Tipo.ACESSO) != user.acesso_pendente
                or (not user.has_usable_password() and not user.acesso_pendente)):
            return None
        url = url_site(reverse("area_cliente:definir_senha", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)), "token": token_acesso.make_token(user),
        }))
        convite = item.tipo == EntregaEmail.Tipo.ACESSO
        return {"assunto": "Seu acesso à área do cliente" if convite else "Recuperação de senha",
                "titulo": "Bem-vindo à sua área do cliente." if convite else "Vamos recuperar seu acesso.",
                "texto": "Defina sua senha para acompanhar seus projetos e manutenções." if convite else "Recebemos uma solicitação para criar uma nova senha para sua conta.",
                "nome": user.get_full_name() or user.username, "usuario": user.username,
                "url": url, "botao": "Definir minha senha", "acesso": True,
                "validade_horas": settings.PASSWORD_RESET_TIMEOUT // 3600}
    if not settings.EMAIL_NOTIFICACOES_ATIVAS:
        return None
    sol = item.solicitacao
    if not sol or not sol.visivel_cliente or sol.cliente_id != user.pk:
        return None
    model = {"atualizacao": AtualizacaoSolicitacao, "mensagem": MensagemSolicitacao, "arquivo": ArquivoSolicitacao}.get(item.tipo)
    obj = model.objects.filter(pk=item.referencia_id, solicitacao=sol).first() if model else None
    if not obj or not getattr(obj, "visivel_cliente", True):
        return None
    para_equipe = getattr(obj, "origem", None) == Origem.CLIENTE
    if para_equipe != item.para_equipe:
        return None
    if para_equipe:
        if not settings.EMAIL_EQUIPE or item.destinatario != settings.EMAIL_EQUIPE:
            return None
        path = reverse("painel:atendimento", args=[sol.pk])
    else:
        if user.acesso_pendente or not email_exclusivo(user) or item.destinatario.casefold() != user.email.strip().casefold():
            return None
        path = sol.get_absolute_url()
    textos = {"atualizacao": "Há uma atualização no andamento do atendimento.",
              "mensagem": "Uma nova mensagem está disponível na conversa do atendimento.",
              "arquivo": "Um novo arquivo foi disponibilizado no atendimento."}
    return {"assunto": "Novidade no atendimento", "titulo": textos[item.tipo],
            "texto": f"Acesse o site para consultar {sol.referencia} e continuar o acompanhamento.",
            "nome": "Danilo" if para_equipe else user.get_full_name() or user.username,
            "url": url_site(path), "botao": "Acompanhar atendimento", "acesso": False}


def processar_entrega(pk):
    # A atualização condicional impede que dois processos enviem o mesmo registro juntos.
    if not EntregaEmail.objects.filter(pk=pk, estado__in=("pendente", "falha")).update(
            estado="enviando", tentativas=F("tentativas") + 1, processado_em=timezone.now(), resultado=""):
        return False
    item = EntregaEmail.objects.select_related("cliente", "solicitacao").get(pk=pk)
    try:
        context = contexto_entrega(item)
        if context is None:
            estado, resultado = "cancelado", "Cadastro, visibilidade ou validade mudou; o e-mail não foi enviado."
        else:
            context["site_url"] = url_site(reverse("core:home"))
            email = EmailMultiAlternatives(subject="Danilo Oliveira · " + context["assunto"],
                body=render_to_string("comunicacao/email.txt", context), from_email=settings.DEFAULT_FROM_EMAIL,
                to=[item.destinatario], reply_to=[settings.EMAIL_REPLY_TO] if settings.EMAIL_REPLY_TO else None)
            email.attach_alternative(render_to_string("comunicacao/email.html", context), "text/html")
            if email.send() != 1:
                raise RuntimeError("O backend não confirmou o envio.")
            backend = settings.MAILERS["default"]["BACKEND"]
            if backend == "django.core.mail.backends.console.EmailBackend" and context["acesso"]:
                # A saída MIME do console pode quebrar a URL com "=\n".
                # Exiba uma cópia literal só neste backend de desenvolvimento.
                print("\nLINK DE ACESSO PARA TESTE LOCAL - COPIE A URL COMPLETA:")
                print(context["url"])
                print("FIM DO LINK DE ACESSO\n")
            simulado = backend in ("django.core.mail.backends.console.EmailBackend", "django.core.mail.backends.filebased.EmailBackend", "django.core.mail.backends.locmem.EmailBackend", "django.core.mail.backends.dummy.EmailBackend")
            estado = "simulado" if simulado else "enviado"
            resultado = "Modo de desenvolvimento; não entregue à caixa de entrada." if simulado else "Aceito pelo servidor; a entrega à caixa de entrada depende do provedor."
    except Exception as exc:
        # Não registrar tokens, corpos de e-mail, destinatários ou credenciais na exceção.
        logger.warning("Falha no e-mail %s (%s)", item.pk, type(exc).__name__)
        estado, resultado = "falha", "Falha no envio. Confira a configuração de e-mail e tente novamente."
    EntregaEmail.objects.filter(pk=pk, estado="enviando").update(estado=estado, resultado=resultado, processado_em=timezone.now())
    return estado in ("simulado", "enviado")
