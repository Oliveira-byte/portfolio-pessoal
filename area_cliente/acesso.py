from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import PasswordResetConfirmView
from django.db import transaction
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import FormView, TemplateView
from django.core.exceptions import ValidationError

from accounts.acesso import clientes_sem_privilegios, token_acesso
from accounts.limites import permitir_recuperacao
from comunicacao.services import solicitar_acesso


class RecuperarAcessoForm(forms.Form):
    email = forms.EmailField(label="E-mail cadastrado", max_length=254,
        widget=forms.EmailInput(attrs={"class": "p5-input", "autocomplete": "email", "autocapitalize": "none"}))


class DefinirSenhaForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "p5-input", "autocomplete": "new-password"})

    def save(self, commit=True):
        self.user.acesso_pendente = False
        return super().save(commit=commit)


@method_decorator(never_cache, name="dispatch")
@method_decorator(sensitive_post_parameters(), name="dispatch")
class RecuperarAcessoView(FormView):
    template_name = "area_cliente/recuperar_acesso.html"
    form_class = RecuperarAcessoForm
    success_url = reverse_lazy("area_cliente:recuperacao_solicitada")

    def form_valid(self, form):
        email = form.cleaned_data["email"].strip()
        if permitir_recuperacao(self.request, email):
            users = list(clientes_sem_privilegios().filter(is_active=True, email__iexact=email)[:2])
            if len(users) == 1:
                try:
                    solicitar_acesso(users[0])
                except ValidationError:
                    pass
        # Sempre a mesma resposta: não revela cadastro, suspensão ou limite de envio.
        return super().form_valid(form)


@method_decorator(never_cache, name="dispatch")
class RecuperacaoSolicitadaView(TemplateView):
    template_name = "area_cliente/recuperacao_solicitada.html"


@method_decorator(never_cache, name="dispatch")
@method_decorator(sensitive_post_parameters(), name="dispatch")
class DefinirSenhaView(PasswordResetConfirmView):
    template_name = "area_cliente/definir_senha.html"
    form_class = DefinirSenhaForm
    token_generator = token_acesso
    success_url = reverse_lazy("area_cliente:acesso_definido")
    post_reset_login = False

    def dispatch(self, *args, **kwargs):
        response = super().dispatch(*args, **kwargs)
        response["Referrer-Policy"] = "same-origin"
        return response

    def form_valid(self, form):
        with transaction.atomic():
            user = type(self.user).objects.select_for_update().get(pk=self.user.pk)
            if not self.token_generator.check_token(user, self.request.session.get("_password_reset_token")):
                self.validlink = False
                return self.render_to_response(self.get_context_data())
            form.user = user
            return super().form_valid(form)


@method_decorator(never_cache, name="dispatch")
class AcessoDefinidoView(TemplateView):
    template_name = "area_cliente/acesso_definido.html"
