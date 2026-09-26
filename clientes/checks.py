from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured
from .storage import private_root


@register()
def check_private_storage(app_configs, **kwargs):
    try:
        private_root()
    except ImproperlyConfigured as exc:
        return [Error(str(exc), id="clientes.E001")]
    return []
