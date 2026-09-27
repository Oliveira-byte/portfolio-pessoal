from .models import ConfiguracaoContato
from .seo import metadados


def canais_contato(request):
    config = ConfiguracaoContato.objects.first() or ConfiguracaoContato()
    return {**metadados(request), "contato_email": config.email, "contato_whatsapp_url": config.whatsapp_url, "contato_whatsapp_numero": config.whatsapp if config.whatsapp_url else ""}
