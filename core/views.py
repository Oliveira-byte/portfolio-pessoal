from django.shortcuts import render


def home(request):
    return render(request, "core/home.html")


def sobre(request):
    return render(request, "core/sobre.html")


def curriculo(request):
    return render(request, "core/curriculo.html")


def competencias(request):
    return render(request, "core/competencias.html")


def contato(request):
    return render(request, "core/contato.html")


def servicos(request):
    return render(request, "core/servicos.html")
