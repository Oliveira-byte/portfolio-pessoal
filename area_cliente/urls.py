from django.urls import path

from .views import (
    AlterarSenhaView, EntrarView, MinhaContaView, PainelView, SairView,
    SenhaAlteradaView, SolicitacaoDetalheView,
)

app_name = "area_cliente"

urlpatterns = [
    path("", PainelView.as_view(), name="painel"),
    path("minha-conta/", MinhaContaView.as_view(), name="minha_conta"),
    path("solicitacoes/<int:pk>/", SolicitacaoDetalheView.as_view(), name="solicitacao_detalhe"),
    path("entrar/", EntrarView.as_view(), name="entrar"),
    path("sair/", SairView.as_view(), name="sair"),
    path("alterar-senha/", AlterarSenhaView.as_view(), name="alterar_senha"),
    path("senha-alterada/", SenhaAlteradaView.as_view(), name="senha_alterada"),
]
