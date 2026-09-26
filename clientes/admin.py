from django.contrib import admin
from django import forms
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_GET

from .downloads import resposta_download

from .models import ArquivoSolicitacao, AtualizacaoSolicitacao, Origem, Solicitacao


class AtualizacaoInline(admin.StackedInline):
    model = AtualizacaoSolicitacao
    extra = 0
    fields = ("titulo", "mensagem", "visivel_cliente", "status_registrado", "progresso_registrado", "autor", "criado_em")
    readonly_fields = ("status_registrado", "progresso_registrado", "autor", "criado_em")


@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "cliente", "tipo", "status", "progresso", "prazo", "visivel_cliente")
    list_filter = ("status", "tipo", "visivel_cliente")
    search_fields = ("titulo", "cliente__username", "cliente__email", "cliente__first_name", "cliente__last_name")
    autocomplete_fields = ("cliente",)
    list_select_related = ("cliente",)
    readonly_fields = ("criado_em", "atualizado_em", "central_arquivos")
    inlines = (AtualizacaoInline,)
    fieldsets = (
        ("Contratação", {"fields": ("cliente", "tipo", "titulo", "descricao")}),
        ("Andamento", {"fields": ("status", "progresso", "proximo_passo", "data_inicio", "prazo")}),
        ("Visibilidade", {"fields": ("visivel_cliente",)}),
        ("Arquivos da contratação", {"fields": ("central_arquivos",)}),
        ("Registro", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    @admin.display(description="Arquivos")
    def central_arquivos(self, obj):
        if not obj.pk:
            return "Salve a contratação para enviar arquivos."
        return format_html('<a href="{}?solicitacao__id__exact={}">Ver arquivos ({})</a> · <a href="{}?solicitacao={}">Enviar arquivo</a>', reverse("admin:clientes_arquivosolicitacao_changelist"), obj.pk, obj.arquivos.count(), reverse("admin:clientes_arquivosolicitacao_add"), obj.pk)

    def save_model(self, request, obj, form, change):
        anterior = Solicitacao.objects.get(pk=obj.pk) if change else None
        super().save_model(request, obj, form, change)
        mudou = anterior and (anterior.status != obj.status or anterior.progresso != obj.progresso)
        if not anterior or mudou:
            AtualizacaoSolicitacao.objects.create(
                solicitacao=obj,
                titulo="Andamento atualizado" if anterior else "Solicitação cadastrada",
                mensagem=f"{obj.get_status_display()} · Progresso informado: {obj.progresso}%.",
                status_registrado=obj.status, progresso_registrado=obj.progresso,
                autor=request.user,
            )

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            if obj._state.adding:
                obj.autor = request.user
                obj.status_registrado = form.instance.status
                obj.progresso_registrado = form.instance.progresso
            obj.save()
        formset.save_m2m()


class ArquivoAdminForm(forms.ModelForm):
    class Meta:
        model = ArquivoSolicitacao
        fields = "__all__"
        widgets = {"arquivo": forms.FileInput()}


@admin.register(ArquivoSolicitacao)
class ArquivoSolicitacaoAdmin(admin.ModelAdmin):
    form = ArquivoAdminForm
    list_display = ("titulo", "solicitacao", "origem", "visivel_cliente", "criado_em", "baixar")
    list_filter = ("origem", "visivel_cliente")
    search_fields = ("titulo", "nome_original", "solicitacao__titulo", "solicitacao__cliente__username")
    autocomplete_fields = ("solicitacao",)
    list_select_related = ("solicitacao", "enviado_por")

    def get_fields(self, request, obj=None):
        if obj:
            return ("solicitacao", "titulo", "baixar", "visivel_cliente", "nome_original", "tamanho", "origem", "enviado_por", "criado_em")
        return ("solicitacao", "titulo", "arquivo", "visivel_cliente")

    def get_readonly_fields(self, request, obj=None):
        return ("solicitacao", "baixar", "nome_original", "tamanho", "origem", "enviado_por", "criado_em") if obj else ()

    @admin.display(description="Download privado")
    def baixar(self, obj):
        return format_html('<a href="{}">Baixar arquivo</a>', reverse("admin:clientes_arquivo_download", args=[obj.pk]))

    def get_urls(self):
        return [path("<int:pk>/download/", self.admin_site.admin_view(require_GET(self.download)), name="clientes_arquivo_download")] + super().get_urls()

    def download(self, request, pk):
        obj = get_object_or_404(ArquivoSolicitacao, pk=pk)
        if not self.has_view_permission(request, obj):
            raise PermissionDenied
        return resposta_download(obj)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.enviado_por = request.user
            obj.origem = Origem.EQUIPE
        super().save_model(request, obj, form, change)
