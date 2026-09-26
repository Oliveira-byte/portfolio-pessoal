from io import BytesIO, StringIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Projeto, Tecnologia


class PortfolioEtapa4Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.publico = Projeto.objects.create(
            titulo="Projeto público", slug="publico", resumo="Resumo público",
            descricao="Descrição pública", publicado=True,
        )
        cls.rascunho = Projeto.objects.create(
            titulo="Projeto reservado", slug="rascunho", resumo="Resumo reservado",
            descricao="Conteúdo reservado",
        )

    def test_listagem_exibe_apenas_publicados(self):
        response = self.client.get(reverse("portfolio:projetos"))
        self.assertContains(response, "Projeto público")
        self.assertNotContains(response, "Projeto reservado")
        self.assertContains(response, self.publico.get_absolute_url())

    def test_detalhe_publicado_exibe_conteudo_e_tecnologias(self):
        self.publico.tecnologias.add(Tecnologia.objects.create(nome="Python"))
        response = self.client.get(self.publico.get_absolute_url())
        self.assertContains(response, "Descrição pública")
        self.assertContains(response, "Python")
        self.assertNotContains(response, "Ver repositório")

    def test_rascunho_e_slug_inexistente_retornam_404(self):
        for slug in ["rascunho", "inexistente"]:
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(reverse("portfolio:projeto_detalhe", kwargs={"slug": slug})).status_code, 404)

    def test_despublicar_remove_acesso_ao_detalhe(self):
        self.publico.publicado = False
        self.publico.save()
        self.assertEqual(self.client.get(self.publico.get_absolute_url()).status_code, 404)

    def test_estado_vazio(self):
        Projeto.objects.all().update(publicado=False)
        self.assertContains(self.client.get(reverse("portfolio:projetos")), "Novos projetos a caminho.")

    def test_ordenacao_prioriza_destaque_e_ordem(self):
        primeiro = Projeto.objects.create(titulo="Destaque", slug="destaque", resumo="Teste", descricao="Teste", publicado=True, destaque=True, ordem=99)
        self.publico.ordem = 1
        self.publico.save()
        segundo = Projeto.objects.create(titulo="Outro", slug="outro", resumo="Teste", descricao="Teste", publicado=True, ordem=0)
        response = self.client.get(reverse("portfolio:projetos"))
        self.assertEqual(list(response.context["projetos"]), [primeiro, segundo, self.publico])

    def test_texto_cadastrado_e_escapado(self):
        self.publico.descricao = '<script>alert("teste")</script>'
        self.publico.save()
        response = self.client.get(self.publico.get_absolute_url())
        self.assertNotContains(response, '<script>alert(')
        self.assertContains(response, '&lt;script&gt;')

    def test_links_aceitam_apenas_http_e_https(self):
        for link in ["javascript:alert(1)", "ftp://example.com/arquivo"]:
            with self.subTest(link=link):
                self.publico.link_site = link
                with self.assertRaises(ValidationError):
                    self.publico.full_clean()
        self.publico.link_site = "https://example.com/projeto"
        self.publico.full_clean()

    def test_comando_preserva_edicoes_e_nao_duplica(self):
        call_command("cadastrar_projetos_iniciais", stdout=StringIO())
        atlas = Projeto.objects.get(slug="atlas-semi-joias")
        atlas.titulo = "Título editado"
        atlas.publicado = False
        atlas.save()
        atlas.tecnologias.clear()
        call_command("cadastrar_projetos_iniciais", stdout=StringIO())
        atlas.refresh_from_db()
        self.assertEqual(atlas.titulo, "Título editado")
        self.assertFalse(atlas.publicado)
        self.assertEqual(atlas.tecnologias.count(), 0)
        self.assertEqual(Projeto.objects.filter(slug__in=["atlas-semi-joias", "portfolio-pessoal"]).count(), 2)

    def test_admin_exige_login(self):
        response = self.client.get(reverse("admin:portfolio_projeto_add"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)

    def test_admin_cadastra_projeto_com_capa(self):
        user = get_user_model().objects.create_superuser(username="admin_teste", password="senha-apenas-de-teste")
        self.client.force_login(user)
        imagem = BytesIO()
        Image.new("RGB", (80, 50), color="navy").save(imagem, format="PNG")
        with TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            response = self.client.post(reverse("admin:portfolio_projeto_add"), {
                "titulo": "Projeto com imagem", "slug": "com-imagem",
                "resumo": "Resumo", "descricao": "Descrição",
                "status": Projeto.Status.DESENVOLVIMENTO,
                "capa_estilo": Projeto.CapaEstilo.PADRAO,
                "capa": SimpleUploadedFile("capa.png", imagem.getvalue(), content_type="image/png"),
                "capa_alt": "Capa azul", "ordem": "0", "publicado": "on", "_save": "Salvar",
            })
            self.assertEqual(response.status_code, 302)
            projeto = Projeto.objects.get(slug="com-imagem")
            self.assertTrue(projeto.capa.storage.exists(projeto.capa.name))
            response = self.client.get(projeto.get_absolute_url())
            self.assertContains(response, projeto.capa.url)
            self.assertContains(response, 'alt="Capa azul"')
