from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db.models import Q


def clientes_sem_privilegios():
    return get_user_model().objects.filter(is_staff=False, is_superuser=False).exclude(
        Q(user_permissions__isnull=False) | Q(groups__permissions__isnull=False)
    ).distinct()


def cliente_apto(user):
    return bool(user and user.is_active and clientes_sem_privilegios().filter(pk=user.pk).exists())


def email_exclusivo(user):
    return bool(user.email and not get_user_model().objects.filter(email__iexact=user.email.strip()).exclude(pk=user.pk).exists())


class TokenAcessoCliente(PasswordResetTokenGenerator):
    key_salt = "accounts.acesso.TokenAcessoCliente"

    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + str(user.versao_acesso) + str(user.is_active) + str(user.acesso_pendente)

    def check_token(self, user, token):
        return cliente_apto(user) and email_exclusivo(user) and super().check_token(user, token)


token_acesso = TokenAcessoCliente()
