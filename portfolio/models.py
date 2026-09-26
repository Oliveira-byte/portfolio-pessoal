from django.core.validators import FileExtensionValidator, URLValidator
from django.db import models
from django.urls import reverse


class Tecnologia(models.Model):
    nome = models.CharField("nome", max_length=60, unique=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "tecnologia"
        verbose_name_plural = "tecnologias"

    def __str__(self):
        return self.nome


class Projeto(models.Model):
    class Status(models.TextChoices):
        DESENVOLVIMENTO = "desenvolvimento", "Em desenvolvimento"
        CONCLUIDO = "concluido", "Concluído"
        PAUSADO = "pausado", "Pausado"

    class CapaEstilo(models.TextChoices):
        PADRAO = "padrao", "Azul e cinza"
        ATLAS = "atlas", "Atlas Semi-Joias"

    titulo = models.CharField("título", max_length=140)
    slug = models.SlugField(
        "endereço da página", max_length=160, unique=True,
        help_text="Ex.: atlas-semi-joias. Evite alterar depois de divulgar o link.",
    )
    categoria = models.CharField("categoria", max_length=80, blank=True)
    resumo = models.CharField("resumo", max_length=280)
    descricao = models.TextField("apresentação do projeto")
    desafio = models.TextField("o desafio", blank=True)
    solucao = models.TextField("minha contribuição", blank=True)
    aprendizados = models.TextField("aprendizados e próximos passos", blank=True)
    tecnologias = models.ManyToManyField(
        Tecnologia, verbose_name="tecnologias", related_name="projetos", blank=True,
    )
    status = models.CharField(
        "status", max_length=20, choices=Status.choices,
        default=Status.DESENVOLVIMENTO,
    )
    capa = models.ImageField(
        "imagem de capa", upload_to="projetos/capas/%Y/%m/", blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        help_text="Opcional. JPG, PNG ou WebP; prefira uma imagem horizontal.",
    )
    capa_alt = models.CharField("descrição da imagem", max_length=180, blank=True)
    capa_estilo = models.CharField(
        "capa sem imagem", max_length=12, choices=CapaEstilo.choices,
        default=CapaEstilo.PADRAO,
    )
    link_site = models.URLField(
        "link do projeto", max_length=500, blank=True,
        validators=[URLValidator(schemes=["http", "https"])],
    )
    link_repositorio = models.URLField(
        "link do repositório", max_length=500, blank=True,
        validators=[URLValidator(schemes=["http", "https"])],
    )
    publicado = models.BooleanField(
        "publicado", default=False,
        help_text="Exibe o projeto na listagem e libera sua página individual.",
    )
    destaque = models.BooleanField("destaque", default=False)
    ordem = models.PositiveIntegerField(
        "ordem", default=0, help_text="Dentro do mesmo grupo, números menores aparecem primeiro.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ("-destaque", "ordem", "-criado_em", "pk")
        verbose_name = "projeto"
        verbose_name_plural = "projetos"

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse("portfolio:projeto_detalhe", kwargs={"slug": self.slug})
