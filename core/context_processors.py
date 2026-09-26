from .models import ConfiguracaoContato


def canais_contato(request):
    config = ConfiguracaoContato.objects.first() or ConfiguracaoContato()
    return {"contato_email": config.email, "contato_whatsapp_url": config.whatsapp_url, "contato_whatsapp_numero": config.whatsapp if config.whatsapp_url else ""}
