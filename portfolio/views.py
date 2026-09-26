from django.shortcuts import get_object_or_404, render

from .models import Projeto


def projetos(request):
    publicados = Projeto.objects.filter(publicado=True).prefetch_related("tecnologias")
    return render(request, "portfolio/projetos.html", {"projetos": publicados})


def projeto_detalhe(request, slug):
    projeto = get_object_or_404(
        Projeto.objects.filter(publicado=True).prefetch_related("tecnologias"),
        slug=slug,
    )
    return render(request, "portfolio/projeto_detalhe.html", {"projeto": projeto})
