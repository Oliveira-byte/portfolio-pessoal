from django.urls import path

from .views import AlterarSenhaView, EntrarView, PainelView, SairView, SenhaAlteradaView

app_name = "area_cliente"

urlpatterns = [
    path("", PainelView.as_view(), name="painel"),
    path("entrar/", EntrarView.as_view(), name="entrar"),
    path("sair/", SairView.as_view(), name="sair"),
    path("alterar-senha/", AlterarSenhaView.as_view(), name="alterar_senha"),
    path("senha-alterada/", SenhaAlteradaView.as_view(), name="senha_alterada"),
]
