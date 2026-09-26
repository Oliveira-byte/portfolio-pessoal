from django.urls import path

from . import views


app_name = "core"


urlpatterns = [
    path("", views.home, name="home"),
    path("servicos/", views.servicos, name="servicos"),
    path("sobre/", views.sobre, name="sobre"),
    path("curriculo/", views.curriculo, name="curriculo"),
    path("competencias/", views.competencias, name="competencias"),
    path("contato/", views.contato, name="contato"),
]