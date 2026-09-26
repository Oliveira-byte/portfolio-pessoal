from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Modelo de usuário personalizado do projeto.

    Inicialmente utiliza os campos padrão do Django,
    permitindo futuras expansões sem precisarmos
    substituir o modelo de usuário depois.
    """

    def __str__(self):
        return self.get_full_name() or self.username