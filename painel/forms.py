from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from clientes.models import Solicitacao, OrdemManutencao, AtualizacaoSolicitacao, ArquivoSolicitacao, MensagemSolicitacao
from core.models import ConfiguracaoContato
from portfolio.models import Projeto, Tecnologia
from .permissions import clientes_gerenciaveis


class EstiloForm:
    grupos = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "g-check"
            else:
                field.widget.attrs["class"] = "g-input"
            if isinstance(field, forms.DateTimeField):
                field.widget = forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "g-input"})
                field.input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
            elif isinstance(field, forms.DateField):
                field.widget = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "g-input"})
                field.input_formats = ["%Y-%m-%d"]
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 4

    def secoes(self):
        grupos = self.grupos or (("Informações", tuple(self.fields)),)
        return [(titulo, [self[name] for name in names if name in self.fields]) for titulo, names in grupos]


class EmailClienteMixin:
    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and get_user_model().objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este e-mail já está associado a outra conta. Use um e-mail exclusivo para o cliente.")
        return email


class ClienteCriarForm(EmailClienteMixin, EstiloForm, forms.ModelForm):
    modo_acesso = forms.ChoiceField(label="Como o cliente receberá o acesso?", required=False,
        choices=(("convite", "Convite por e-mail — cliente define a senha"), ("manual", "Definir senha manualmente")), initial="convite")
    password1 = forms.CharField(label="Senha inicial (somente no modo manual)", required=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirme a senha inicial", required=False, widget=forms.PasswordInput)
    grupos = (("Dados do cliente", ("first_name", "last_name", "email", "username")),
              ("Acesso à conta", ("modo_acesso", "password1", "password2")))

    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email", "username", "modo_acesso", "password1", "password2")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Já existe uma conta com este usuário.")
        return username

    def clean(self):
        data = super().clean()
        # Mantém compatibilidade com formulários da etapa anterior que enviam senhas.
        modo = data.get("modo_acesso") or ("manual" if data.get("password1") else "convite")
        data["modo_acesso"] = modo
        if modo == "convite" and not data.get("email"):
            self.add_error("email", "Informe o e-mail do cliente para preparar o convite.")
        if modo == "manual":
            if not data.get("password1"):
                self.add_error("password1", "Informe a senha inicial.")
            if data.get("password1") != data.get("password2"):
                self.add_error("password2", "As senhas não coincidem.")
        return data

    def _post_clean(self):
        super()._post_clean()
        if self.cleaned_data.get("modo_acesso") == "manual" and self.cleaned_data.get("password1"):
            try:
                validate_password(self.cleaned_data["password1"], self.instance)
            except forms.ValidationError as error:
                self.add_error("password1", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.acesso_pendente = self.cleaned_data["modo_acesso"] == "convite"
        if user.acesso_pendente:
            user.set_unusable_password()
        else:
            user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class ClienteEditarForm(EmailClienteMixin, EstiloForm, forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email", "username", "is_active")
        help_texts = {"is_active": "Desmarque para suspender o acesso. O histórico de atendimentos será preservado."}


class SenhaClienteForm(EstiloForm, SetPasswordForm):
    def save(self, commit=True):
        self.user.acesso_pendente = False
        return super().save(commit=commit)


class AtendimentoForm(EstiloForm, forms.ModelForm):
    grupos = (
        ("Identificação", ("cliente", "tipo", "titulo", "descricao")),
        ("Andamento", ("status", "progresso", "proximo_passo", "data_inicio", "prazo")),
        ("Acesso do cliente", ("visivel_cliente",)),
    )
    class Meta:
        model = Solicitacao
        fields = ("cliente", "tipo", "titulo", "descricao", "status", "progresso", "proximo_passo", "data_inicio", "prazo", "visivel_cliente")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = clientes_gerenciaveis()
        if self.instance.pk:
            self.fields["cliente"].queryset = get_user_model().objects.filter(pk=self.instance.cliente_id)
            self.fields["cliente"].disabled = True
        self.fields["tipo"].choices = [(k, v) for k, v in Solicitacao.Tipo.choices if k != "manutencao"]


class ManutencaoForm(EstiloForm, forms.ModelForm):
    grupos = (
        ("Ordem de serviço", ("cliente", "titulo", "descricao", "visivel_cliente")),
        ("Equipamento", ("equipamento", "marca", "modelo", "numero_serie", "relato_cliente", "acessorios", "condicao_recebimento")),
        ("Acompanhamento do cliente", ("etapa", "proximo_passo", "data_inicio", "prazo", "diagnostico_publico", "servico_realizado")),
        ("Orçamento combinado", ("orcamento_acordado", "detalhes_orcamento", "valor_servicos", "valor_pecas", "valor_logistica", "data_acordo", "pagamento_combinado")),
        ("Coleta e entrega", ("recebimento", "coleta_prevista", "recebido_em", "devolucao", "devolucao_prevista", "entregue_em", "endereco_atendimento", "observacoes_logistica")),
        ("Anotações internas", ("anotacoes_internas",)),
    )
    class Meta:
        model = OrdemManutencao
        fields = ("cliente", "titulo", "descricao", "visivel_cliente", "equipamento", "marca", "modelo", "numero_serie", "relato_cliente", "acessorios", "condicao_recebimento", "etapa", "proximo_passo", "data_inicio", "prazo", "diagnostico_publico", "servico_realizado", "orcamento_acordado", "detalhes_orcamento", "valor_servicos", "valor_pecas", "valor_logistica", "data_acordo", "pagamento_combinado", "recebimento", "coleta_prevista", "recebido_em", "devolucao", "devolucao_prevista", "entregue_em", "endereco_atendimento", "observacoes_logistica", "anotacoes_internas")
        labels = {"descricao": "Serviço solicitado"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = clientes_gerenciaveis()
        if self.instance.pk:
            self.fields["cliente"].queryset = get_user_model().objects.filter(pk=self.instance.cliente_id)
            self.fields["cliente"].disabled = True


class AtualizacaoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = AtualizacaoSolicitacao
        fields = ("titulo", "mensagem", "visivel_cliente")


class MensagemForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = MensagemSolicitacao
        fields = ("texto",)
        widgets = {"texto": forms.Textarea(attrs={"maxlength": 5000, "placeholder": "Escreva sua resposta ao cliente…"})}


class ArquivoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = ArquivoSolicitacao
        fields = ("titulo", "arquivo", "visivel_cliente")
        widgets = {"arquivo": forms.FileInput(attrs={"accept": ".pdf,.docx,.xlsx,.pptx,.txt,.csv,.png,.jpg,.jpeg,.webp,.zip"})}
        help_texts = {"arquivo": "Até 10 MB. PDF, DOCX, XLSX, PPTX, TXT, CSV, PNG, JPG, WEBP ou ZIP."}


class ArquivoEditarForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = ArquivoSolicitacao
        fields = ("titulo", "visivel_cliente")


class PortfolioForm(EstiloForm, forms.ModelForm):
    grupos = (
        ("Apresentação", ("titulo", "slug", "categoria", "resumo", "descricao")),
        ("Conteúdo", ("desafio", "solucao", "aprendizados", "tecnologias", "status")),
        ("Capa e links", ("capa", "capa_alt", "capa_estilo", "link_site", "link_repositorio")),
        ("Publicação", ("publicado", "destaque", "ordem")),
    )
    class Meta:
        model = Projeto
        fields = ("titulo", "slug", "categoria", "resumo", "descricao", "desafio", "solucao", "aprendizados", "tecnologias", "status", "capa", "capa_alt", "capa_estilo", "link_site", "link_repositorio", "publicado", "destaque", "ordem")


class TecnologiaForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Tecnologia
        fields = ("nome",)


class ContatoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = ConfiguracaoContato
        fields = ("email", "whatsapp", "whatsapp_ativo")
