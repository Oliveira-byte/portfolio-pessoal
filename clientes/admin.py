from django.contrib import admin

from .models import AtualizacaoSolicitacao, Solicitacao


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
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = (AtualizacaoInline,)
    fieldsets = (
        ("Contratação", {"fields": ("cliente", "tipo", "titulo", "descricao")}),
        ("Andamento", {"fields": ("status", "progresso", "proximo_passo", "data_inicio", "prazo")}),
        ("Visibilidade", {"fields": ("visivel_cliente",)}),
        ("Registro", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

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
