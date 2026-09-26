from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", include("core.urls")),

    path(
        "projetos/",
        include("portfolio.urls")
    ),

    path("area-cliente/", include("area_cliente.urls")),
]