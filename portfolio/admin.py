from django.contrib import admin

from .models import Projeto, Tecnologia


@admin.register(Tecnologia)
class TecnologiaAdmin(admin.ModelAdmin):
    search_fields = ("nome",)


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "status", "publicado", "destaque", "ordem", "atualizado_em")
    list_filter = ("publicado", "destaque", "status", "tecnologias")
    search_fields = ("titulo", "resumo", "descricao")
    prepopulated_fields = {"slug": ("titulo",)}
    filter_horizontal = ("tecnologias",)
    readonly_fields = ("criado_em", "atualizado_em")
    fieldsets = (
        ("Apresentação", {"fields": ("titulo", "slug", "categoria", "resumo", "descricao")}),
        ("Detalhes", {"fields": ("desafio", "solucao", "aprendizados", "tecnologias", "status")}),
        ("Capa", {"fields": ("capa", "capa_alt", "capa_estilo")}),
        ("Links", {"fields": ("link_site", "link_repositorio")}),
        ("Publicação", {"fields": ("publicado", "destaque", "ordem")}),
        ("Registro", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )
