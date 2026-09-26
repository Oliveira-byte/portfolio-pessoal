from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordChangeDoneView, PasswordChangeView,
)
from django.db.models import Max, Q
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, TemplateView

from clientes.models import AtualizacaoSolicitacao, Solicitacao

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
            Solicitacao.objects.para_cliente(usuario).annotate(
                ultima_novidade=Max("atualizacoes__criado_em", filter=Q(atualizacoes__visivel_cliente=True)),
            )
        )
        ativas = [item for item in solicitacoes if not item.encerrada]
        # Pendências de resposta aparecem primeiro; em seguida, prazos vencidos.
        ativas.sort(key=lambda item: (item.status != Solicitacao.Status.AGUARDANDO, not item.prazo_vencido))
        context.update({
            "solicitacoes_ativas": ativas,
            "solicitacoes_encerradas": [item for item in solicitacoes if item.encerrada],
            "total_ativas": len(ativas),
            "total_aguardando": sum(item.status == Solicitacao.Status.AGUARDANDO for item in ativas),
            "total_concluidas": sum(item.status == Solicitacao.Status.CONCLUIDA for item in solicitacoes),
            "tem_solicitacoes": bool(solicitacoes),
            "ultimas_atualizacoes": AtualizacaoSolicitacao.objects.filter(
                solicitacao__cliente=usuario, solicitacao__visivel_cliente=True,
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
        return Solicitacao.objects.para_cliente(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["atualizacoes"] = self.object.atualizacoes.filter(visivel_cliente=True)
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
