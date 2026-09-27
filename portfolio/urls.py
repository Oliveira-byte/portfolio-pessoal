from django.urls import path

from . import views

app_name = "portfolio"

urlpatterns = [
    path("", views.projetos, name="projetos"),
    path("<slug:slug>/capa/", views.projeto_capa, name="projeto_capa"),
    path("<slug:slug>/", views.projeto_detalhe, name="projeto_detalhe"),
]
