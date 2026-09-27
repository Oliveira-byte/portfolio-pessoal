from functools import wraps
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.urls import reverse
from django.views.decorators.cache import never_cache
from clientes.models import Solicitacao, OrdemManutencao


def permitido(user, model, action="view"):
    opts = model._meta
    return user.is_active and user.is_staff and (
        user.has_perm(f"{opts.app_label}.{action}_{opts.model_name}")
        or (action == "view" and user.has_perm(f"{opts.app_label}.change_{opts.model_name}"))
    )


def exigir(user, model, action="view"):
    if not permitido(user, model, action):
        raise PermissionDenied


def equipe_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("painel:entrar"))
        if not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return never_cache(wrapped)


def atendimentos_permitidos(user):
    qs = Solicitacao.objects.select_related("cliente", "ordemmanutencao")
    filtro = Q(pk__in=[])
    if permitido(user, Solicitacao):
        filtro |= ~Q(tipo=Solicitacao.Tipo.MANUTENCAO)
    if permitido(user, OrdemManutencao):
        filtro |= Q(tipo=Solicitacao.Tipo.MANUTENCAO)
    return qs.filter(filtro)


def clientes_gerenciaveis():
    # O painel de clientes não gerencia contas administrativas ou com permissões.
    return get_user_model().objects.filter(is_staff=False, is_superuser=False).exclude(
        Q(user_permissions__isnull=False) | Q(groups__permissions__isnull=False)
    ).distinct().order_by("first_name", "username")
