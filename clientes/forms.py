from django import forms
from .models import ArquivoSolicitacao, MensagemSolicitacao, Solicitacao


class ArquivoClienteForm(forms.ModelForm):
    class Meta:
        model = ArquivoSolicitacao
        fields = ("titulo", "arquivo")
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "p5-input", "placeholder": "Ex.: Referências para o projeto"}),
            "arquivo": forms.FileInput(attrs={"class": "p5-input", "accept": ".pdf,.docx,.xlsx,.pptx,.txt,.csv,.png,.jpg,.jpeg,.webp,.zip"}),
        }
        help_texts = {"arquivo": "Até 10 MB. PDF, documentos do Office, TXT, CSV, imagens (PNG, JPG, WEBP) ou ZIP."}


class MensagemClienteForm(forms.ModelForm):
    class Meta:
        model = MensagemSolicitacao
        fields = ("texto",)
        widgets = {"texto": forms.Textarea(attrs={"class": "p5-input", "rows": 4, "placeholder": "Escreva sua dúvida, feedback ou resposta…", "maxlength": 5000})}
        help_texts = {"texto": "Até 5.000 caracteres. A resposta ficará disponível nesta conversa."}


class SolicitacaoDigitalForm(forms.ModelForm):
    class Meta:
        model = Solicitacao
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [item for item in Solicitacao.Tipo.choices if item[0] != Solicitacao.Tipo.MANUTENCAO]
