from django.http import FileResponse, Http404


def resposta_download(arquivo):
    try:
        stream = arquivo.arquivo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Arquivo indisponível.")
    response = FileResponse(stream, as_attachment=True, filename=arquivo.nome_original, content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response
