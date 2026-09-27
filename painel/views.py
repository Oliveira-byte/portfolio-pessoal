from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from comunicacao.models import EntregaEmail
from comunicacao.services import solicitar_acesso, processar_entrega
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from clientes.downloads import resposta_download
from clientes.models import Solicitacao, OrdemManutencao, ArquivoSolicitacao, AtualizacaoSolicitacao, MensagemSolicitacao, Origem
from clientes.services import salvar_atendimento
from core.models import ConfiguracaoContato
from portfolio.models import Projeto, Tecnologia
from .forms import (ClienteCriarForm, ClienteEditarForm, SenhaClienteForm, AtendimentoForm, ManutencaoForm,
                    AtualizacaoForm, MensagemForm, ArquivoForm, ArquivoEditarForm, PortfolioForm, TecnologiaForm, ContatoForm)
from .permissions import equipe_required, exigir, permitido, atendimentos_permitidos, clientes_gerenciaveis


@method_decorator(never_cache, name="dispatch")
class EntrarView(LoginView):
    authentication_form = AdminAuthenticationForm
    template_name = "painel/entrar.html"
    next_page = reverse_lazy("painel:inicio")


@method_decorator(never_cache, name="dispatch")
class SairView(LogoutView):
    next_page = reverse_lazy("painel:entrar")


def acessos(user):
    modelos = {"clientes": get_user_model(), "projetos": Solicitacao, "manutencoes": OrdemManutencao,
               "mensagens": MensagemSolicitacao, "arquivos": ArquivoSolicitacao, "portfolio": Projeto,
               "tecnologias": Tecnologia, "contato": ConfiguracaoContato}
    resultado = {}
    for nome, model in modelos.items():
        for action in ("view", "add", "change", "delete"):
            resultado[f"{nome}_{action}"] = permitido(user, model, action)
    return resultado


def tela(request, template, context=None, status=200):
    context = {**(context or {}), "access": acessos(request.user)}
    return render(request, "painel/" + template, context, status=status)


def pagina(request, qs, key="pagina", tamanho=20, anchor=""):
    page = Paginator(qs, tamanho).get_page(request.GET.get(key))
    for attr, numero in (("anterior_url", page.number - 1), ("proxima_url", page.number + 1)):
        params = request.GET.copy()
        params[key] = numero
        setattr(page, attr, "?" + params.urlencode() + ("#" + anchor if anchor else ""))
    return page


def registrar(request, obj, texto, action=CHANGE):
    LogEntry.objects.create(user_id=request.user.pk, content_type=ContentType.objects.get_for_model(obj),
                            object_id=str(obj.pk), object_repr=str(obj)[:200], action_flag=action, change_message=texto)


def carregar_atendimento(request, pk, action="view"):
    obj = get_object_or_404(atendimentos_permitidos(request.user), pk=pk)
    model = OrdemManutencao if obj.eh_manutencao else Solicitacao
    exigir(request.user, model, action)
    return obj.manutencao if obj.eh_manutencao else obj


def formulario(request, form, titulo, voltar, secao, descricao="", status=200):
    return tela(request, "formulario.html", {"form": form, "titulo": titulo, "voltar": voltar, "secao": secao, "descricao": descricao}, status)


@equipe_required
@require_GET
def inicio(request):
    qs = atendimentos_permitidos(request.user)
    abertos = qs.exclude(status__in=(Solicitacao.Status.CONCLUIDA, Solicitacao.Status.CANCELADA))
    novas = MensagemSolicitacao.objects.filter(solicitacao__in=qs, origem=Origem.CLIENTE, lida_equipe_em__isnull=True)
    pode_mensagens = permitido(request.user, MensagemSolicitacao)
    pendencias = abertos.filter(Q(prazo__lt=timezone.localdate()) | Q(status=Solicitacao.Status.AGUARDANDO)).order_by("prazo", "pk")[:6]
    return tela(request, "inicio.html", {
        "secao": "inicio", "abertos": abertos.count(), "atrasados": abertos.filter(prazo__lt=timezone.localdate()).count(),
        "manutencoes": abertos.filter(tipo="manutencao").count(), "novas": novas.count() if pode_mensagens else None,
        "pendencias": pendencias, "recentes": qs[:6], "mensagens_recentes": novas.select_related("solicitacao", "solicitacao__cliente")[:5] if pode_mensagens else [],
    })


@equipe_required
@require_GET
def clientes(request):
    exigir(request.user, get_user_model())
    qs = clientes_gerenciaveis()
    busca = request.GET.get("q", "").strip()[:150]
    if busca:
        qs = qs.filter(Q(username__icontains=busca) | Q(first_name__icontains=busca) | Q(last_name__icontains=busca) | Q(email__icontains=busca))
    if request.GET.get("estado") in ("ativo", "inativo"):
        qs = qs.filter(is_active=request.GET["estado"] == "ativo")
    return tela(request, "clientes.html", {"secao": "clientes", "clientes": pagina(request, qs), "busca": busca})


@equipe_required
@require_http_methods(["GET", "POST"])
def cliente_form(request, pk=None):
    exigir(request.user, get_user_model(), "change" if pk else "add")
    obj = get_object_or_404(clientes_gerenciaveis(), pk=pk) if pk else None
    form = (ClienteEditarForm if obj else ClienteCriarForm)(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj = form.save()
            if not pk and obj.acesso_pendente:
                solicitar_acesso(obj)
            registrar(request, obj, "Cadastro do cliente atualizado." if pk else "Cliente cadastrado pelo painel.", CHANGE if pk else ADDITION)
        messages.success(request, "Cliente salvo. Confira o estado do convite abaixo." if not pk and obj.acesso_pendente else "Cliente salvo.")
        return redirect("painel:cliente", pk=obj.pk)
    return formulario(request, form, "Editar cliente" if pk else "Cadastrar cliente", reverse("painel:clientes"), "clientes", "No modo convite, o cliente define a própria senha pelo link enviado ao e-mail cadastrado. Os campos de senha são usados somente no modo manual.", 400 if request.method == "POST" else 200)


@equipe_required
@require_GET
def cliente_detalhe(request, pk):
    exigir(request.user, get_user_model())
    obj = get_object_or_404(clientes_gerenciaveis(), pk=pk)
    qs = atendimentos_permitidos(request.user).filter(cliente=obj)
    return tela(request, "cliente.html", {"secao": "clientes", "cliente": obj, "atendimentos": pagina(request, qs), "emails_acesso": obj.entregas_email.filter(tipo__in=("acesso", "senha"))[:5]})


@equipe_required
@require_http_methods(["GET", "POST"])
def cliente_senha(request, pk):
    exigir(request.user, get_user_model(), "change")
    obj = get_object_or_404(clientes_gerenciaveis(), pk=pk)
    form = SenhaClienteForm(obj, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            registrar(request, obj, "Senha do cliente redefinida pelo painel.")
        messages.success(request, "Senha redefinida. Combine o acesso diretamente com o cliente.")
        return redirect("painel:cliente", pk=pk)
    return formulario(request, form, "Redefinir senha do cliente", reverse("painel:cliente", args=[pk]), "clientes", "A nova senha invalida as sessões anteriores do cliente.", 400 if request.method == "POST" else 200)


@equipe_required
@require_GET
def atendimentos(request, categoria):
    if categoria not in ("projetos", "manutencoes"):
        raise Http404
    manutencao = categoria == "manutencoes"
    exigir(request.user, OrdemManutencao if manutencao else Solicitacao)
    qs = atendimentos_permitidos(request.user)
    qs = qs.filter(tipo="manutencao") if manutencao else qs.exclude(tipo="manutencao")
    busca = request.GET.get("q", "").strip()[:150]
    if busca:
        qs = qs.filter(Q(titulo__icontains=busca) | Q(cliente__username__icontains=busca) | Q(cliente__first_name__icontains=busca) | Q(cliente__last_name__icontains=busca))
    situacao = request.GET.get("situacao", "abertos")
    if situacao == "abertos":
        qs = qs.exclude(status__in=("concluida", "cancelada"))
    elif situacao == "encerrados":
        qs = qs.filter(status__in=("concluida", "cancelada"))
    elif situacao == "atrasados":
        qs = qs.filter(prazo__lt=timezone.localdate()).exclude(status__in=("concluida", "cancelada"))
    if request.GET.get("visibilidade") in ("publico", "interno"):
        qs = qs.filter(visivel_cliente=request.GET["visibilidade"] == "publico")
    return tela(request, "atendimentos.html", {"secao": categoria, "categoria": categoria, "manutencao": manutencao,
        "atendimentos": pagina(request, qs), "busca": busca, "situacao": situacao,
        "pode_criar": permitido(request.user, OrdemManutencao if manutencao else Solicitacao, "add")})


@equipe_required
@require_http_methods(["GET", "POST"])
def atendimento_form(request, categoria=None, pk=None):
    obj = carregar_atendimento(request, pk, "change") if pk else None
    if obj:
        categoria = "manutencoes" if obj.eh_manutencao else "projetos"
    if categoria not in ("projetos", "manutencoes"):
        raise Http404
    model = OrdemManutencao if categoria == "manutencoes" else Solicitacao
    exigir(request.user, model, "change" if obj else "add")
    anterior = model.objects.get(pk=obj.pk) if obj else None
    initial = {}
    if not obj and request.GET.get("cliente", "").isdigit():
        cliente = get_object_or_404(clientes_gerenciaveis(), pk=request.GET["cliente"])
        initial["cliente"] = cliente
    form = (ManutencaoForm if categoria == "manutencoes" else AtendimentoForm)(request.POST or None, instance=obj, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj = salvar_atendimento(form.save(commit=False), request.user, anterior)
            registrar(request, obj, "Atendimento atualizado pelo painel." if pk else "Atendimento cadastrado pelo painel.", CHANGE if pk else ADDITION)
        messages.success(request, "Atendimento salvo. As alterações já estão disponíveis conforme a visibilidade definida.")
        return redirect("painel:atendimento", pk=obj.pk)
    titulo = ("Editar " if obj else "Cadastrar ") + ("manutenção" if categoria == "manutencoes" else "projeto ou serviço")
    voltar = reverse("painel:atendimento", args=[pk]) if pk else reverse("painel:atendimentos", args=[categoria])
    return formulario(request, form, titulo, voltar, categoria, "Revise a visibilidade antes de disponibilizar as informações ao cliente.", 400 if request.method == "POST" else 200)


def detalhe_context(request, obj, **forms):
    ctx = {"secao": "manutencoes" if obj.eh_manutencao else "projetos", "atendimento": obj,
           "manutencao": obj if obj.eh_manutencao else None,
           "pode_editar": permitido(request.user, type(obj), "change"),
           "form_mensagem": forms.get("form_mensagem", MensagemForm(prefix="mensagem")),
           "form_arquivo": forms.get("form_arquivo", ArquivoForm(prefix="arquivo")),
           "form_atualizacao": forms.get("form_atualizacao", AtualizacaoForm(prefix="historico")),
           "pode_atualizar": permitido(request.user, AtualizacaoSolicitacao, "add"),
           "pode_ver_historico": permitido(request.user, AtualizacaoSolicitacao)}
    if ctx["pode_ver_historico"]:
        ctx["historico"] = pagina(request, obj.atualizacoes.all(), "historico", 15, "historico")
    if permitido(request.user, ArquivoSolicitacao):
        ctx["arquivos"] = pagina(request, obj.arquivos.all(), "arquivos", 10, "arquivos")
    if permitido(request.user, MensagemSolicitacao):
        pag = pagina(request, obj.mensagens.all(), "conversa", 30, "mensagens")
        conversa = list(reversed(list(pag.object_list)))
        if request.method == "GET":
            ids = [m.pk for m in conversa if m.origem == Origem.CLIENTE and m.lida_equipe_em is None]
            MensagemSolicitacao.objects.filter(pk__in=ids, lida_equipe_em__isnull=True).update(lida_equipe_em=timezone.now())
        ctx.update(conversa=conversa, conversa_pagina=pag)
    return ctx


@equipe_required
@require_GET
def atendimento_detalhe(request, pk):
    return tela(request, "atendimento.html", detalhe_context(request, carregar_atendimento(request, pk)))


@equipe_required
@require_POST
def enviar_mensagem(request, pk):
    obj = carregar_atendimento(request, pk)
    exigir(request.user, MensagemSolicitacao, "add")
    form = MensagemForm(request.POST, prefix="mensagem")
    if form.is_valid():
        with transaction.atomic():
            msg = form.save(commit=False)
            msg.solicitacao = obj
            msg.autor = request.user
            msg.origem = Origem.EQUIPE
            msg.save()
            registrar(request, msg, "Resposta enviada ao cliente.", ADDITION)
        messages.success(request, "Mensagem enviada ao cliente.")
        return redirect(reverse("painel:atendimento", args=[pk]) + "#mensagens")
    return tela(request, "atendimento.html", detalhe_context(request, obj, form_mensagem=form), 400)


@equipe_required
@require_POST
def adicionar_atualizacao(request, pk):
    obj = carregar_atendimento(request, pk)
    exigir(request.user, AtualizacaoSolicitacao, "add")
    form = AtualizacaoForm(request.POST, prefix="historico")
    if form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            item.solicitacao = obj
            item.autor = request.user
            if not obj.eh_manutencao:
                item.status_registrado, item.progresso_registrado = obj.status, obj.progresso
            item.save()
            registrar(request, item, "Atualização registrada no atendimento.", ADDITION)
        messages.success(request, "Atualização registrada.")
        return redirect(reverse("painel:atendimento", args=[pk]) + "#historico")
    return tela(request, "atendimento.html", detalhe_context(request, obj, form_atualizacao=form), 400)


@equipe_required
@require_POST
def enviar_arquivo(request, pk):
    obj = carregar_atendimento(request, pk)
    exigir(request.user, ArquivoSolicitacao, "add")
    form = ArquivoForm(request.POST, request.FILES, prefix="arquivo")
    if form.is_valid():
        with transaction.atomic():
            arquivo = form.save(commit=False)
            arquivo.solicitacao = obj
            arquivo.enviado_por = request.user
            arquivo.origem = Origem.EQUIPE
            arquivo.save()
            registrar(request, arquivo, "Arquivo anexado ao atendimento.", ADDITION)
        messages.success(request, "Arquivo enviado.")
        return redirect(reverse("painel:atendimento", args=[pk]) + "#arquivos")
    return tela(request, "atendimento.html", detalhe_context(request, obj, form_arquivo=form), 400)


def carregar_arquivo(request, pk, arquivo_pk, action="view"):
    obj = carregar_atendimento(request, pk)
    exigir(request.user, ArquivoSolicitacao, action)
    return get_object_or_404(ArquivoSolicitacao, pk=arquivo_pk, solicitacao_id=obj.pk)


@equipe_required
@require_GET
def arquivo_download(request, pk, arquivo_pk):
    return resposta_download(carregar_arquivo(request, pk, arquivo_pk))


@equipe_required
@require_http_methods(["GET", "POST"])
def arquivo_editar(request, pk, arquivo_pk):
    obj = carregar_arquivo(request, pk, arquivo_pk, "change")
    form = ArquivoEditarForm(request.POST or None, instance=obj)
    voltar = reverse("painel:atendimento", args=[pk]) + "#arquivos"
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            registrar(request, obj, "Título ou visibilidade do arquivo atualizado.")
        messages.success(request, "Arquivo atualizado.")
        return redirect(voltar)
    return formulario(request, form, "Editar arquivo", voltar, "arquivos", "Para substituir o conteúdo, envie outro arquivo.", 400 if request.method == "POST" else 200)


@equipe_required
@require_http_methods(["GET", "POST"])
def arquivo_excluir(request, pk, arquivo_pk):
    obj = carregar_arquivo(request, pk, arquivo_pk, "delete")
    voltar = reverse("painel:atendimento", args=[pk]) + "#arquivos"
    if request.method == "POST":
        with transaction.atomic():
            registrar(request, obj, "Arquivo excluído do atendimento.", DELETION)
            obj.delete()
        messages.success(request, "Arquivo excluído.")
        return redirect(voltar)
    return tela(request, "confirmar.html", {"titulo": "Excluir arquivo", "nome": obj.titulo, "descricao": "O registro e o arquivo serão removidos. Esta ação não pode ser desfeita.", "voltar": voltar, "secao": "arquivos"})


@equipe_required
@require_GET
def mensagens_lista(request):
    exigir(request.user, MensagemSolicitacao)
    qs = MensagemSolicitacao.objects.filter(solicitacao__in=atendimentos_permitidos(request.user)).select_related("solicitacao", "solicitacao__cliente")
    filtro = request.GET.get("filtro", "novas")
    if filtro == "novas":
        qs = qs.filter(origem=Origem.CLIENTE, lida_equipe_em__isnull=True)
    elif filtro == "cliente":
        qs = qs.filter(origem=Origem.CLIENTE)
    busca = request.GET.get("q", "").strip()[:150]
    if busca:
        qs = qs.filter(Q(texto__icontains=busca) | Q(solicitacao__titulo__icontains=busca) | Q(solicitacao__cliente__username__icontains=busca))
    return tela(request, "mensagens.html", {"secao": "mensagens", "mensagens_lista": pagina(request, qs), "filtro": filtro, "busca": busca})


@equipe_required
@require_GET
def arquivos_lista(request):
    exigir(request.user, ArquivoSolicitacao)
    qs = ArquivoSolicitacao.objects.filter(solicitacao__in=atendimentos_permitidos(request.user)).select_related("solicitacao", "solicitacao__cliente")
    busca = request.GET.get("q", "").strip()[:150]
    if busca:
        qs = qs.filter(Q(titulo__icontains=busca) | Q(nome_original__icontains=busca) | Q(solicitacao__titulo__icontains=busca))
    return tela(request, "arquivos.html", {"secao": "arquivos", "arquivos": pagina(request, qs), "busca": busca})


@equipe_required
@require_GET
def portfolio_lista(request):
    exigir(request.user, Projeto)
    qs = Projeto.objects.all()
    busca = request.GET.get("q", "").strip()[:150]
    if busca:
        qs = qs.filter(titulo__icontains=busca)
    return tela(request, "portfolio.html", {"secao": "portfolio", "projetos": pagina(request, qs), "busca": busca})


@equipe_required
@require_http_methods(["GET", "POST"])
def portfolio_form(request, pk=None):
    exigir(request.user, Projeto, "change" if pk else "add")
    obj = get_object_or_404(Projeto, pk=pk) if pk else None
    form = PortfolioForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj = form.save()
            registrar(request, obj, "Projeto do portfólio salvo pelo painel.", CHANGE if pk else ADDITION)
        messages.success(request, "Projeto do portfólio salvo.")
        return redirect("painel:portfolio")
    return formulario(request, form, "Editar projeto do portfólio" if pk else "Novo projeto do portfólio", reverse("painel:portfolio"), "portfolio", "Publicado libera a página no site. Desmarque para manter o projeto como rascunho.", 400 if request.method == "POST" else 200)


@equipe_required
@require_http_methods(["GET", "POST"])
def tecnologias(request, pk=None):
    exigir(request.user, Tecnologia)
    obj = get_object_or_404(Tecnologia, pk=pk) if pk else None
    form = TecnologiaForm(request.POST or None, instance=obj)
    if request.method == "POST":
        exigir(request.user, Tecnologia, "change" if pk else "add")
        if form.is_valid():
            with transaction.atomic():
                obj = form.save()
                registrar(request, obj, "Tecnologia salva pelo painel.", CHANGE if pk else ADDITION)
            messages.success(request, "Tecnologia salva.")
            return redirect("painel:tecnologias")
    return tela(request, "tecnologias.html", {"secao": "portfolio", "tecnologias": pagina(request, Tecnologia.objects.all()), "form": form, "editando": bool(pk)}, 400 if request.method == "POST" else 200)


@equipe_required
@require_http_methods(["GET", "POST"])
def contato(request):
    obj = ConfiguracaoContato.objects.first()
    exigir(request.user, ConfiguracaoContato, "change" if obj else "add")
    form = ContatoForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            novo = form.save()
            registrar(request, novo, "Canais de atendimento atualizados.", CHANGE if obj else ADDITION)
        messages.success(request, "Contatos atualizados no site.")
        return redirect("painel:contato")
    return formulario(request, form, "Contatos do site", reverse("painel:inicio"), "contato", "O WhatsApp aparece no site somente quando estiver configurado e ativado.", 400 if request.method == "POST" else 200)


@equipe_required
@require_GET
def abrir_mensagem(request, pk):
    exigir(request.user, MensagemSolicitacao)
    item = get_object_or_404(MensagemSolicitacao.objects.filter(solicitacao__in=atendimentos_permitidos(request.user)), pk=pk)
    anteriores_na_lista = item.solicitacao.mensagens.filter(Q(criado_em__gt=item.criado_em) | Q(criado_em=item.criado_em, pk__gt=item.pk)).count()
    numero = anteriores_na_lista // 30 + 1
    return redirect(reverse("painel:atendimento", args=[item.solicitacao_id]) + f"?conversa={numero}#mensagem-{item.pk}")


@equipe_required
@require_http_methods(["GET", "POST"])
def cliente_convite(request, pk):
    exigir(request.user, get_user_model(), "change")
    obj = get_object_or_404(clientes_gerenciaveis(), pk=pk)
    if request.method == "POST":
        try:
            with transaction.atomic():
                entrega = solicitar_acesso(obj, renovar=True)
                registrar(request, obj, "Link de acesso solicitado pelo painel.")
            entrega.refresh_from_db()
            messages.success(request, "Solicitação registrada: " + entrega.get_estado_display() + ".")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("painel:cliente", pk=pk)
    return tela(request, "convite.html", {"secao": "clientes", "cliente": obj})


@equipe_required
@require_GET
def emails(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    qs = EntregaEmail.objects.select_related("cliente")
    estado = request.GET.get("estado", "")
    if estado in EntregaEmail.Estado.values:
        qs = qs.filter(estado=estado)
    backend = settings.MAILERS["default"]["BACKEND"]
    return tela(request, "emails.html", {"secao": "emails", "emails": pagina(request, qs),
        "estado": estado, "estados": EntregaEmail.Estado.choices,
        "modo_console": backend != "django.core.mail.backends.smtp.EmailBackend",
        "envio_imediato": settings.EMAIL_ENVIO_IMEDIATO, "equipe_configurada": bool(settings.EMAIL_EQUIPE)})


@equipe_required
@require_POST
def email_repetir(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    obj = get_object_or_404(EntregaEmail, pk=pk)
    if obj.estado in ("pendente", "falha"):
        processar_entrega(obj.pk)
        obj.refresh_from_db()
        registrar(request, obj, "Processamento de e-mail solicitado pelo painel.")
        messages.info(request, obj.get_estado_display() + ". " + obj.resultado)
    else:
        messages.info(request, "Este registro já foi processado. Para renovar um link, use o cadastro do cliente.")
    return redirect("painel:emails")
