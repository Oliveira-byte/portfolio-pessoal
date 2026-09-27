from django.shortcuts import redirect, render
from django.urls import reverse
from .servicos_catalogo import SERVICOS


def home(request):
    return render(request, "core/home.html")


def sobre(request):
    return render(request, "core/sobre.html")


def curriculo(request):
    return render(request, "core/curriculo.html")


def competencias(request):
    return redirect(reverse("core:curriculo") + "#competencias", permanent=True)


def contato(request):
    return render(request, "core/contato.html")


def servicos(request):
    return render(request, "core/servicos.html", {
        "servicos_formularios": SERVICOS,
        "servicos_digitais": [s for s in SERVICOS if s["grupo"] == "Serviços Digitais"],
        "servicos_equipamentos": [s for s in SERVICOS if s["grupo"] == "Computadores e notebooks"],
    })
