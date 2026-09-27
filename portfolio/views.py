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
    return render(request, "portfolio/projeto_detalhe.html", {"projeto": projeto, "seo_titulo": f"{projeto.titulo} | Danilo Oliveira", "seo_descricao": projeto.resumo})


def projeto_capa(request, slug):
    """Serve apenas capas de projetos publicados, sem expor MEDIA_ROOT inteiro."""
    from django.http import FileResponse, Http404
    import mimetypes

    projeto = get_object_or_404(Projeto, slug=slug, publicado=True)
    if not projeto.capa:
        raise Http404("Projeto sem imagem de capa.")
    try:
        arquivo = projeto.capa.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Imagem não encontrada.")
    response = FileResponse(arquivo, content_type=mimetypes.guess_type(projeto.capa.name)[0] or "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response
