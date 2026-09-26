"""Arquivos de contratos nunca recebem uma URL pública de mídia."""
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.storage import FileSystemStorage


EXTENSOES_PERMITIDAS = {"pdf", "docx", "xlsx", "pptx", "txt", "csv", "png", "jpg", "jpeg", "webp", "zip"}
LIMITE_ARQUIVO = 10 * 1024 * 1024


def private_root():
    root = Path(getattr(settings, "PRIVATE_FILES_ROOT", settings.BASE_DIR / "private_uploads")).resolve()
    publicos = [settings.MEDIA_ROOT, settings.STATIC_ROOT]
    publicos.extend(item[1] if isinstance(item, (tuple, list)) else item for item in settings.STATICFILES_DIRS)
    for publico in publicos:
        if publico and root.is_relative_to(Path(publico).resolve()):
            raise ImproperlyConfigured("PRIVATE_FILES_ROOT precisa ficar fora das pastas públicas de mídia e arquivos estáticos.")
    return root


class PrivateFileStorage(FileSystemStorage):
    @property
    def base_location(self):
        return str(private_root())

    @property
    def location(self):
        return str(private_root())

    def url(self, name):
        raise ValueError("Arquivo privado: use a rota de download autenticada.")


def private_storage():
    return PrivateFileStorage()


def nome_seguro(nome):
    return str(nome).replace("\\", "/").rsplit("/", 1)[-1]


def caminho_arquivo(instance, filename):
    extensao = Path(filename).suffix.lower()
    return f"solicitacoes/{instance.solicitacao_id}/{uuid4().hex}{extensao}"


def validar_arquivo(arquivo):
    if Path(arquivo.name).suffix.lower().lstrip(".") not in EXTENSOES_PERMITIDAS:
        raise ValidationError("Formato não permitido. Envie PDF, DOCX, XLSX, PPTX, TXT, CSV, PNG, JPG, WEBP ou ZIP.")
    if arquivo.size > LIMITE_ARQUIVO:
        raise ValidationError("O arquivo deve ter no máximo 10 MB.")
    if arquivo.size == 0:
        raise ValidationError("O arquivo está vazio.")
