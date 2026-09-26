from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordChangeDoneView, PasswordChangeView,
)
from django.db.models import Count, Max, Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, TemplateView

from clientes.models import ArquivoSolicitacao, AtualizacaoSolicitacao, MensagemSolicitacao, Origem, Solicitacao
from clientes.forms import ArquivoClienteForm, MensagemClienteForm
from clientes.downloads import resposta_download

from .forms import LoginClienteForm, SenhaClienteForm


@method_decorator(never_cache, name="dispatch")
class EntrarView(LoginView):
    template_name = "area_cliente/entrar.html"
    authentication_form = LoginClienteForm
    next_page = reverse_lazy("area_cliente:painel")
    # O Django verifica o destino 'next' e rejeita redirecionamentos externos.


@method_decorator(never_cache, name="dispatch")
class SairView(LogoutView):
    def get_success_url(self):
        return reverse_lazy("core:home")


@method_decorator(never_cache, name="dispatch")
class PainelView(LoginRequiredMixin, TemplateView):
    template_name = "area_cliente/painel.html"
    login_url = reverse_lazy("area_cliente:entrar")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
        nome = usuario.get_full_name().strip()
        context["nome_exibicao"] = nome or usuario.get_username()
        solicitacoes = list(
            Solicitacao.objects.para_cliente(usuario).select_related("ordemmanutencao").annotate(
                novas_mensagens=Count("mensagens", filter=Q(mensagens__origem=Origem.EQUIPE, mensagens__lida_cliente_em__isnull=True), distinct=True),
                ultima_novidade=Max("atualizacoes__criado_em", filter=Q(atualizacoes__visivel_cliente=True)),
            )
        )
        categoria = self.request.GET.get("categoria", "todos")
        if categoria not in ("todos", "digital", "manutencao"):
            categoria = "todos"
        context.update({"categoria": categoria, "total_manutencoes": sum(item.eh_manutencao for item in solicitacoes), "total_digitais": sum(not item.eh_manutencao for item in solicitacoes), "tem_cadastros": bool(solicitacoes)})
        if categoria != "todos":
            solicitacoes = [item for item in solicitacoes if item.eh_manutencao == (categoria == "manutencao")]
        ativas = [item for item in solicitacoes if not item.encerrada]
        # Pendências de resposta aparecem primeiro; em seguida, prazos vencidos.
        ativas.sort(key=lambda item: (item.status != Solicitacao.Status.AGUARDANDO, not item.prazo_vencido))
        context.update({
            "solicitacoes_ativas": ativas,
            "solicitacoes_encerradas": [item for item in solicitacoes if item.encerrada],
            "total_ativas": len(ativas),
            "total_novas_mensagens": sum(item.novas_mensagens for item in solicitacoes),
            "total_aguardando": sum(item.status == Solicitacao.Status.AGUARDANDO for item in ativas),
            "total_concluidas": sum(item.status == Solicitacao.Status.CONCLUIDA for item in solicitacoes),
            "tem_solicitacoes": bool(solicitacoes),
            "ultimas_atualizacoes": AtualizacaoSolicitacao.objects.filter(
                solicitacao__cliente=usuario, solicitacao__visivel_cliente=True, solicitacao_id__in=[item.pk for item in solicitacoes],
                visivel_cliente=True,
            ).select_related("solicitacao")[:4],
        })
        return context


@method_decorator(never_cache, name="dispatch")
class MinhaContaView(LoginRequiredMixin, TemplateView):
    template_name = "area_cliente/minha_conta.html"
    login_url = reverse_lazy("area_cliente:entrar")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["nome_exibicao"] = self.request.user.get_full_name().strip() or self.request.user.get_username()
        return context


@method_decorator(never_cache, name="dispatch")
class SolicitacaoDetalheView(LoginRequiredMixin, DetailView):
    template_name = "area_cliente/solicitacao_detalhe.html"
    context_object_name = "solicitacao"
    login_url = reverse_lazy("area_cliente:entrar")

    def get_queryset(self):
        # Não há exceção para staff: este é o portal do cliente, não o admin.
        return Solicitacao.objects.para_cliente(self.request.user).select_related("ordemmanutencao")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(contexto_colaboracao(self.request, self.object, marcar_lidas=self.request.method == "GET"))
        return context


@method_decorator(never_cache, name="dispatch")
class AlterarSenhaView(LoginRequiredMixin, PasswordChangeView):
    template_name = "area_cliente/alterar_senha.html"
    form_class = SenhaClienteForm
    login_url = reverse_lazy("area_cliente:entrar")
    success_url = reverse_lazy("area_cliente:senha_alterada")


@method_decorator(never_cache, name="dispatch")
class SenhaAlteradaView(LoginRequiredMixin, PasswordChangeDoneView):
    template_name = "area_cliente/senha_alterada.html"
    login_url = reverse_lazy("area_cliente:entrar")


def contexto_colaboracao(request, solicitacao, *, marcar_lidas=False, **formularios):
    pagina = Paginator(solicitacao.mensagens.all(), 30).get_page(request.GET.get("conversa"))
    conversa = list(reversed(list(pagina.object_list)))
    if marcar_lidas:
        ids = [item.pk for item in conversa if item.origem == Origem.EQUIPE and item.lida_cliente_em is None]
        MensagemSolicitacao.objects.filter(pk__in=ids, lida_cliente_em__isnull=True).update(lida_cliente_em=timezone.now())
    arquivos_pagina = Paginator(solicitacao.arquivos.filter(visivel_cliente=True), 10).get_page(request.GET.get("arquivos"))
    return {
        "solicitacao": solicitacao,
        "manutencao": solicitacao.manutencao,
        "atualizacoes": solicitacao.atualizacoes.filter(visivel_cliente=True),
        "arquivos_pagina": arquivos_pagina,
        "conversa_pagina": pagina,
        "conversa": conversa,
        "form_arquivo": formularios.get("form_arquivo", ArquivoClienteForm(prefix="anexo")),
        "form_mensagem": formularios.get("form_mensagem", MensagemClienteForm(prefix="conversa")),
    }


@never_cache
@login_required(login_url="area_cliente:entrar")
@require_POST
def enviar_mensagem(request, pk):
    solicitacao = get_object_or_404(Solicitacao.objects.para_cliente(request.user), pk=pk)
    form = MensagemClienteForm(request.POST, prefix="conversa")
    if form.is_valid():
        mensagem = form.save(commit=False)
        mensagem.solicitacao = solicitacao
        mensagem.autor = request.user
        mensagem.origem = Origem.CLIENTE
        mensagem.save()
        messages.success(request, "Mensagem enviada. Você poderá acompanhar a resposta por aqui.")
        return redirect(solicitacao.get_absolute_url() + "#mensagens")
    return render(request, "area_cliente/solicitacao_detalhe.html", contexto_colaboracao(request, solicitacao, form_mensagem=form), status=400)


@never_cache
@login_required(login_url="area_cliente:entrar")
@require_POST
def enviar_arquivo(request, pk):
    solicitacao = get_object_or_404(Solicitacao.objects.para_cliente(request.user), pk=pk)
    form = ArquivoClienteForm(request.POST, request.FILES, prefix="anexo")
    if form.is_valid():
        arquivo = form.save(commit=False)
        arquivo.solicitacao = solicitacao
        arquivo.enviado_por = request.user
        arquivo.origem = Origem.CLIENTE
        arquivo.visivel_cliente = True
        arquivo.save()
        messages.success(request, "Arquivo enviado e vinculado à sua contratação.")
        return redirect(solicitacao.get_absolute_url() + "#arquivos")
    return render(request, "area_cliente/solicitacao_detalhe.html", contexto_colaboracao(request, solicitacao, form_arquivo=form), status=400)


@never_cache
@login_required(login_url="area_cliente:entrar")
@require_GET
def arquivo_download(request, pk, arquivo_pk):
    solicitacao = get_object_or_404(Solicitacao.objects.para_cliente(request.user), pk=pk)
    arquivo = get_object_or_404(ArquivoSolicitacao, pk=arquivo_pk, solicitacao=solicitacao, visivel_cliente=True)
    return resposta_download(arquivo)
