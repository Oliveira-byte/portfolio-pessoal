from django.urls import path

from .views import (
    AlterarSenhaView, EntrarView, MinhaContaView, PainelView, SairView,
    SenhaAlteradaView, SolicitacaoDetalheView, enviar_mensagem, enviar_arquivo, arquivo_download,
)

app_name = "area_cliente"

urlpatterns = [
    path("", PainelView.as_view(), name="painel"),
    path("minha-conta/", MinhaContaView.as_view(), name="minha_conta"),
    path("solicitacoes/<int:pk>/", SolicitacaoDetalheView.as_view(), name="solicitacao_detalhe"),
    path("solicitacoes/<int:pk>/mensagens/enviar/", enviar_mensagem, name="enviar_mensagem"),
    path("solicitacoes/<int:pk>/arquivos/enviar/", enviar_arquivo, name="enviar_arquivo"),
    path("solicitacoes/<int:pk>/arquivos/<int:arquivo_pk>/download/", arquivo_download, name="arquivo_download"),
    path("entrar/", EntrarView.as_view(), name="entrar"),
    path("sair/", SairView.as_view(), name="sair"),
    path("alterar-senha/", AlterarSenhaView.as_view(), name="alterar_senha"),
    path("senha-alterada/", SenhaAlteradaView.as_view(), name="senha_alterada"),
]
