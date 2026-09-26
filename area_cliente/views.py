from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordChangeDoneView, PasswordChangeView,
)
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

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
