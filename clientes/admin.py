from django.contrib import admin
from django import forms
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_GET

from .downloads import resposta_download
from .forms import SolicitacaoDigitalForm

from .models import ArquivoSolicitacao, AtualizacaoSolicitacao, MensagemSolicitacao, OrdemManutencao, Origem, Solicitacao


class AtualizacaoInline(admin.StackedInline):
    model = AtualizacaoSolicitacao
    extra = 0
    fields = ("titulo", "mensagem", "visivel_cliente", "status_registrado", "progresso_registrado", "autor", "criado_em")
    readonly_fields = ("status_registrado", "progresso_registrado", "autor", "criado_em")


@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    form = SolicitacaoDigitalForm
    list_display = ("titulo", "cliente", "tipo", "status", "progresso", "prazo", "visivel_cliente", "mensagens_novas")
    list_filter = ("status", "tipo", "visivel_cliente")
    search_fields = ("titulo", "cliente__username", "cliente__email", "cliente__first_name", "cliente__last_name")
    autocomplete_fields = ("cliente",)
    list_select_related = ("cliente",)
    readonly_fields = ("criado_em", "atualizado_em", "central_arquivos", "central_mensagens")
    inlines = (AtualizacaoInline,)
    fieldsets = (
        ("Contratação", {"fields": ("cliente", "tipo", "titulo", "descricao")}),
        ("Andamento", {"fields": ("status", "progresso", "proximo_passo", "data_inicio", "prazo")}),
        ("Visibilidade", {"fields": ("visivel_cliente",)}),
        ("Arquivos e conversa", {"fields": ("central_arquivos", "central_mensagens")}),
        ("Registro", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        if obj and obj.eh_manutencao:
            if not self.has_view_or_change_permission(request, obj) or request.method != "GET":
                raise PermissionDenied
            return redirect("admin:clientes_ordemmanutencao_change", object_id=obj.pk)
        return super().change_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if self.model is Solicitacao and request.resolver_match.url_name == "clientes_solicitacao_changelist":
            queryset = queryset.exclude(tipo=Solicitacao.Tipo.MANUTENCAO)
        return queryset.annotate(total_nao_lidas=Count("mensagens", filter=Q(mensagens__origem=Origem.CLIENTE, mensagens__lida_equipe_em__isnull=True), distinct=True)).order_by("-atualizado_em", "-pk")

    @admin.display(description="Mensagens novas", ordering="total_nao_lidas")
    def mensagens_novas(self, obj):
        return format_html('<a href="{}?solicitacao__id__exact={}&leitura=novas">{}</a>', reverse("admin:clientes_mensagemsolicitacao_changelist"), obj.pk, obj.total_nao_lidas)

    @admin.display(description="Arquivos")
    def central_arquivos(self, obj):
        if not obj.pk:
            return "Salve a contratação para enviar arquivos."
        return format_html('<a href="{}?solicitacao__id__exact={}">Ver arquivos ({})</a> · <a href="{}?solicitacao={}">Enviar arquivo</a>', reverse("admin:clientes_arquivosolicitacao_changelist"), obj.pk, obj.arquivos.count(), reverse("admin:clientes_arquivosolicitacao_add"), obj.pk)

    @admin.display(description="Conversa")
    def central_mensagens(self, obj):
        if not obj.pk:
            return "Salve a contratação para iniciar a conversa."
        return format_html('<a href="{}?solicitacao__id__exact={}">Ver mensagens ({})</a> · <a href="{}?solicitacao={}">Enviar mensagem</a>', reverse("admin:clientes_mensagemsolicitacao_changelist"), obj.pk, obj.mensagens.count(), reverse("admin:clientes_mensagemsolicitacao_add"), obj.pk)

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
                obj.progresso_registrado = None if form.instance.eh_manutencao else form.instance.progresso
                if form.instance.eh_manutencao:
                    obj.status_registrado = ""
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


class LeituraEquipeFilter(admin.SimpleListFilter):
    title = "leitura pela equipe"
    parameter_name = "leitura"

    def lookups(self, request, model_admin):
        return (("novas", "Novas do cliente"), ("lidas", "Lidas pela equipe"))

    def queryset(self, request, queryset):
        if self.value() in ("novas", "lidas"):
            return queryset.filter(origem=Origem.CLIENTE, lida_equipe_em__isnull=self.value() == "novas")
        return queryset


@admin.register(MensagemSolicitacao)
class MensagemSolicitacaoAdmin(admin.ModelAdmin):
    list_display = ("resumo", "solicitacao", "origem", "situacao_leitura", "criado_em")
    list_filter = (LeituraEquipeFilter, "origem")
    search_fields = ("texto", "solicitacao__titulo", "solicitacao__cliente__username")
    autocomplete_fields = ("solicitacao",)
    list_select_related = ("solicitacao", "autor")
    actions = ("marcar_lidas",)

    def get_fields(self, request, obj=None):
        if obj:
            return ("solicitacao", "texto", "origem", "autor", "criado_em", "lida_cliente_em", "lida_equipe_em", "responder")
        return ("solicitacao", "texto")

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj else ()

    @admin.display(description="Mensagem")
    def resumo(self, obj):
        return obj.texto[:110]

    @admin.display(description="Leitura")
    def situacao_leitura(self, obj):
        if obj.origem == Origem.CLIENTE:
            return "Lida pela equipe" if obj.lida_equipe_em else "● Nova do cliente"
        return "Lida pelo cliente" if obj.lida_cliente_em else "Enviada ao cliente"

    @admin.display(description="Responder")
    def responder(self, obj):
        return format_html('<a href="{}?solicitacao={}">Enviar resposta nesta contratação</a> · <a href="{}?solicitacao__id__exact={}">Ver conversa</a>', reverse("admin:clientes_mensagemsolicitacao_add"), obj.solicitacao_id, reverse("admin:clientes_mensagemsolicitacao_changelist"), obj.solicitacao_id)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        # Só o objeto efetivamente aberto é marcado; filtros e listagem não alteram leitura.
        response = super().change_view(request, object_id, form_url, extra_context)
        if request.method == "GET" and response.status_code == 200:
            obj = response.context_data.get("original")
            if obj and obj.origem == Origem.CLIENTE and obj.lida_equipe_em is None:
                agora = timezone.now()
                MensagemSolicitacao.objects.filter(pk=obj.pk, lida_equipe_em__isnull=True).update(lida_equipe_em=agora)
                obj.lida_equipe_em = agora
        return response

    @admin.action(description="Marcar mensagens selecionadas como lidas", permissions=["change"])
    def marcar_lidas(self, request, queryset):
        total = queryset.filter(origem=Origem.CLIENTE, lida_equipe_em__isnull=True).update(lida_equipe_em=timezone.now())
        self.message_user(request, f"{total} mensagem(ns) marcada(s) como lida(s).")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.autor = request.user
            obj.origem = Origem.EQUIPE
            super().save_model(request, obj, form, change)


@admin.register(OrdemManutencao)
class OrdemManutencaoAdmin(SolicitacaoAdmin):
    form = forms.ModelForm
    list_display = ("referencia_os", "titulo", "cliente", "equipamento", "etapa", "prazo", "orcamento_acordado", "visivel_cliente", "mensagens_novas")
    list_filter = ("etapa", "equipamento", "orcamento_acordado", "visivel_cliente")
    search_fields = SolicitacaoAdmin.search_fields + ("marca", "modelo", "numero_serie")
    fieldsets = (
        ("Ordem de serviço", {"fields": ("cliente", "titulo", "descricao", "visivel_cliente")}),
        ("Equipamento e recebimento", {"fields": ("equipamento", "marca", "modelo", "numero_serie", "relato_cliente", "acessorios", "condicao_recebimento")}),
        ("Acompanhamento visível ao cliente", {"fields": ("etapa", "proximo_passo", "data_inicio", "prazo", "diagnostico_publico", "servico_realizado")}),
        ("Orçamento combinado por contato", {"fields": ("orcamento_acordado", "detalhes_orcamento", "valor_servicos", "valor_pecas", "valor_logistica", "data_acordo", "pagamento_combinado"), "description": "Valores em negociação ficam internos até marcar o orçamento como acordado. O site não solicita aprovação ao cliente."}),
        ("Coleta e entrega", {"fields": ("recebimento", "coleta_prevista", "recebido_em", "devolucao", "devolucao_prevista", "entregue_em", "endereco_atendimento", "observacoes_logistica")}),
        ("Somente para a administração", {"fields": ("anotacoes_internas",), "classes": ("collapse",)}),
        ("Arquivos e conversa", {"fields": ("central_arquivos", "central_mensagens")}),
        ("Registro", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    @admin.display(description="Ordem de serviço")
    def referencia_os(self, obj):
        return obj.referencia

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return admin.ModelAdmin.change_view(self, request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        anterior = OrdemManutencao.objects.get(pk=obj.pk) if change else None
        admin.ModelAdmin.save_model(self, request, obj, form, change)
        if not anterior or anterior.etapa != obj.etapa:
            AtualizacaoSolicitacao.objects.create(
                solicitacao=obj, titulo="Etapa da manutenção atualizada" if anterior else "Ordem de serviço cadastrada",
                mensagem=obj.get_etapa_display(), autor=request.user,
            )
        campos_acordo = ("detalhes_orcamento", "valor_servicos", "valor_pecas", "valor_logistica", "data_acordo", "pagamento_combinado")
        if obj.orcamento_acordado and (not anterior or not anterior.orcamento_acordado or any(getattr(anterior, campo) != getattr(obj, campo) for campo in campos_acordo)):
            AtualizacaoSolicitacao.objects.create(
                solicitacao=obj, titulo="Orçamento acordado registrado",
                mensagem=f"{obj.detalhes_orcamento}\nTotal acordado: R$ " + format(obj.total_acordado, ".2f").replace(".", ","),
                autor=request.user,
            )
