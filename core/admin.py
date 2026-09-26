from django.contrib import admin
from .models import ConfiguracaoContato


@admin.register(ConfiguracaoContato)
class ConfiguracaoContatoAdmin(admin.ModelAdmin):
    fields = ("email", "whatsapp", "whatsapp_ativo")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not ConfiguracaoContato.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
