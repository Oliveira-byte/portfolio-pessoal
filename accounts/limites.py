from django.core.cache import cache
from django.utils.crypto import salted_hmac


def permitir_recuperacao(request, email):
    # REMOTE_ADDR vem do servidor. Cabeçalhos de proxy não são aceitos diretamente.
    valores = (("ip", request.META.get("REMOTE_ADDR", ""), 5), ("email", email.casefold(), 1))
    for tipo, valor, limite in valores:
        key = "acesso:" + tipo + ":" + salted_hmac("recuperacao", valor).hexdigest()
        if cache.add(key, 1, timeout=60):
            continue
        try:
            if cache.incr(key) > limite:
                return False
        except ValueError:
            cache.add(key, 1, timeout=60)
    return True
