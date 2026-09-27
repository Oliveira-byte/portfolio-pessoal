from django.urls import path

from .views import (
    AlterarSenhaView, EntrarView, MinhaContaView, PainelView, SairView,
    SenhaAlteradaView, SolicitacaoDetalheView, enviar_mensagem, enviar_arquivo, arquivo_download,
)

from .acesso import RecuperarAcessoView, RecuperacaoSolicitadaView, DefinirSenhaView, AcessoDefinidoView

app_name = "area_cliente"

urlpatterns = [
    path("recuperar-acesso/", RecuperarAcessoView.as_view(), name="recuperar_acesso"),
    path("recuperacao-solicitada/", RecuperacaoSolicitadaView.as_view(), name="recuperacao_solicitada"),
    path("definir-senha/<uidb64>/<token>/", DefinirSenhaView.as_view(), name="definir_senha"),
    path("acesso-definido/", AcessoDefinidoView.as_view(), name="acesso_definido"),
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
