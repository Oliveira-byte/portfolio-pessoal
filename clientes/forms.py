from django import forms
from .models import ArquivoSolicitacao


class ArquivoClienteForm(forms.ModelForm):
    class Meta:
        model = ArquivoSolicitacao
        fields = ("titulo", "arquivo")
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "p5-input", "placeholder": "Ex.: Referências para o projeto"}),
            "arquivo": forms.FileInput(attrs={"class": "p5-input", "accept": ".pdf,.docx,.xlsx,.pptx,.txt,.csv,.png,.jpg,.jpeg,.webp,.zip"}),
        }
        help_texts = {"arquivo": "Até 10 MB. PDF, documentos do Office, TXT, CSV, imagens (PNG, JPG, WEBP) ou ZIP."}

