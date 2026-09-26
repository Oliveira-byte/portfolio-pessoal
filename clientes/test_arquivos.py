import errno
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .checks import check_private_storage
from .models import ArquivoSolicitacao, Origem, Solicitacao
from .storage import LIMITE_ARQUIVO, private_root, validar_arquivo


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ArquivosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.dono = User.objects.create_user(username="cliente", password="teste123")
        cls.outro = User.objects.create_user(username="outro", password="teste123")
        cls.admin = User.objects.create_superuser(username="admin", password="teste123")
        cls.staff = User.objects.create_user(username="equipe", is_staff=True)
        cls.projeto = Solicitacao.objects.create(cliente=cls.dono, titulo="Site", descricao="Escopo", progresso=25, visivel_cliente=True)
        cls.oculta = Solicitacao.objects.create(cliente=cls.dono, titulo="Rascunho", descricao="Privado")
        cls.alheia = Solicitacao.objects.create(cliente=cls.outro, titulo="Outro", descricao="Privado", visivel_cliente=True)


    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.private_dir = Path(temp.name) / "privado"
        setting = override_settings(PRIVATE_FILES_ROOT=self.private_dir)
        setting.enable()
        self.addCleanup(setting.disable)
        self.client.force_login(self.dono)


    def upload(self, nome="referencias.txt", dados=b"Referencias para o projeto"):
        return SimpleUploadedFile(nome, dados, content_type="text/plain")


    def arquivo(self, **kwargs):
        dados = dict(solicitacao=self.projeto, titulo="Referências", arquivo=self.upload(), enviado_por=self.admin)
        dados.update(kwargs)
        return ArquivoSolicitacao.objects.create(**dados)


    def endpoint(self, nome, projeto=None):
        return reverse("area_cliente:" + nome, args=[(projeto or self.projeto).pk])


    def download_url(self, arquivo, projeto=None):
        return reverse("area_cliente:arquivo_download", args=[(projeto or self.projeto).pk, arquivo.pk])


    def test_download_autorizado_forca_anexo_sem_cache_e_nome_original(self):
        arquivo = self.arquivo(arquivo=self.upload("referências.txt"))
        response = self.client.get(self.download_url(arquivo))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"Referencias para o projeto")
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        self.assertIn("refer%C3%AAncias.txt", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(Path(arquivo.arquivo.path).is_relative_to(self.private_dir))
        self.assertNotIn("referências", arquivo.arquivo.name)
        with self.assertRaises(ValueError):
            _ = arquivo.arquivo.url


    def test_outro_cliente_staff_e_visitante_nao_baixam(self):
        arquivo = self.arquivo()
        for usuario in (self.outro, self.admin):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.download_url(arquivo)).status_code, 404)
        self.client.logout()
        response = self.client.get(self.download_url(arquivo))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/area-cliente/entrar/", response.url)


    def test_arquivo_oculto_contrato_oculto_e_id_de_outro_contrato(self):
        for arquivo in (self.arquivo(visivel_cliente=False), self.arquivo(solicitacao=self.oculta), self.arquivo(solicitacao=self.alheia)):
            self.assertEqual(self.client.get(self.download_url(arquivo, arquivo.solicitacao)).status_code, 404)
            self.assertEqual(self.client.get(self.download_url(arquivo)).status_code, 404)
        arquivo = self.arquivo()
        self.projeto.visivel_cliente = False
        self.projeto.save()
        self.assertEqual(self.client.get(self.download_url(arquivo)).status_code, 404)


    def test_caminho_adivinhado_nao_e_publico_e_arquivo_ausente_da_404(self):
        arquivo = self.arquivo()
        for prefixo in ("/media/", "/private_uploads/"):
            self.assertEqual(self.client.get(prefixo + arquivo.arquivo.name).status_code, 404)
        arquivo.arquivo.storage.delete(arquivo.arquivo.name)
        self.assertEqual(self.client.get(self.download_url(arquivo)).status_code, 404)


    def test_upload_cliente_ignora_autor_origem_e_contrato_forjados(self):
        response = self.client.post(self.endpoint("enviar_arquivo"), {
            "anexo-titulo": "Briefing", "anexo-arquivo": self.upload(),
            "solicitacao": self.alheia.pk, "origem": "equipe", "enviado_por": self.admin.pk,
            "visivel_cliente": False,
        })
        self.assertRedirects(response, self.projeto.get_absolute_url() + "#arquivos")
        arquivo = ArquivoSolicitacao.objects.get()
        self.assertEqual(arquivo.solicitacao, self.projeto)
        self.assertEqual(arquivo.enviado_por, self.dono)
        self.assertEqual(arquivo.origem, Origem.CLIENTE)
        self.assertTrue(arquivo.visivel_cliente)
        self.assertEqual(arquivo.tamanho, len(b"Referencias para o projeto"))


    def test_upload_invalido_nao_grava_arquivo_e_exibe_erros(self):
        for nome, dados in (("script.html", b"<script>"), ("script.svg", b"<svg/>"), ("vazio.txt", b""), ("grande.pdf", b"a" * (LIMITE_ARQUIVO + 1))):
            response = self.client.post(self.endpoint("enviar_arquivo"), {"anexo-titulo": "Documento", "anexo-arquivo": self.upload(nome, dados)})
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, 'role="alert"', status_code=400)
        self.assertFalse(ArquivoSolicitacao.objects.exists())
        self.assertFalse(self.private_dir.exists())


    def test_limite_exato_aceito_e_validacao_tambem_no_model(self):
        validar_arquivo(self.upload("documento.PDF", b"a" * LIMITE_ARQUIVO))
        with self.assertRaises(ValidationError):
            self.arquivo(arquivo=self.upload("codigo.exe"))


    def test_admin_download_exige_permissao_do_model(self):
        arquivo = self.arquivo(visivel_cliente=False)
        url = reverse("admin:clientes_arquivo_download", args=[arquivo.pk])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(codename="view_arquivosolicitacao"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response.close()
        self.client.force_login(self.dono)
        self.assertEqual(self.client.get(url).status_code, 302)


    def test_admin_cria_arquivo_e_edita_sem_expor_url_publica(self):
        self.client.force_login(self.admin)
        url = reverse("admin:clientes_arquivosolicitacao_add")
        self.assertEqual(self.client.get(url, {"solicitacao": self.projeto.pk}).status_code, 200)
        response = self.client.post(url, {"solicitacao": self.projeto.pk, "titulo": "Entrega", "arquivo": self.upload(), "visivel_cliente": "on", "origem": "cliente"})
        self.assertEqual(response.status_code, 302)
        arquivo = ArquivoSolicitacao.objects.get()
        self.assertEqual(arquivo.origem, Origem.EQUIPE)
        self.assertEqual(arquivo.enviado_por, self.admin)
        url = reverse("admin:clientes_arquivosolicitacao_change", args=[arquivo.pk])
        response = self.client.get(url)
        self.assertContains(response, reverse("admin:clientes_arquivo_download", args=[arquivo.pk]))
        self.assertNotContains(response, 'name="arquivo"')
        response = self.client.post(url, {"titulo": "Entrega revisada", "solicitacao": self.alheia.pk, "arquivo": self.upload("novo.txt")})
        self.assertEqual(response.status_code, 302)
        arquivo.refresh_from_db()
        self.assertEqual(arquivo.titulo, "Entrega revisada")
        self.assertEqual(arquivo.solicitacao, self.projeto)
        self.assertEqual(arquivo.nome_original, "referencias.txt")
        self.assertFalse(arquivo.visivel_cliente)
        self.assertEqual(self.client.get(reverse("admin:clientes_arquivosolicitacao_changelist")).status_code, 200)


    def test_delete_remove_arquivo_so_apos_commit_e_rollback_preserva(self):
        arquivo = self.arquivo()
        path = Path(arquivo.arquivo.path)
        with self.captureOnCommitCallbacks(execute=True):
            arquivo.delete()
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())
        arquivo = self.arquivo()
        path = Path(arquivo.arquivo.path)
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                arquivo.delete()
                raise RuntimeError("Simula falha na transação")
        self.assertTrue(path.exists())
        self.assertEqual(ArquivoSolicitacao.objects.count(), 1)


    def test_substituicao_ou_troca_de_contrato_no_model_bloqueadas(self):
        arquivo = self.arquivo()
        arquivo.arquivo = self.upload("novo.txt")
        with self.assertRaises(ValidationError):
            arquivo.save()
        arquivo.refresh_from_db()
        arquivo.solicitacao = self.alheia
        with self.assertRaises(ValidationError):
            arquivo.save()


    def test_pastas_publicas_rejeitadas(self):
        with tempfile.TemporaryDirectory() as root:
            publico = Path(root) / "publico"
            publico.mkdir()
            for pasta in (publico, publico / "anexos"):
                with override_settings(PRIVATE_FILES_ROOT=pasta, MEDIA_ROOT=publico):
                    with self.assertRaises(ImproperlyConfigured):
                        private_root()
                    self.assertEqual(check_private_storage(None)[0].id, "clientes.E001")
            with override_settings(PRIVATE_FILES_ROOT=publico / "anexos", STATICFILES_DIRS=[("prefixo", publico)]):
                self.assertEqual(check_private_storage(None)[0].id, "clientes.E001")

    def test_alias_simbolico_para_pasta_publica_rejeitado(self):
        with tempfile.TemporaryDirectory() as root:
            publico = Path(root) / "publico"
            publico.mkdir()
            alias = Path(root) / "alias"
            try:
                alias.symlink_to(publico, target_is_directory=True)
            except NotImplementedError:
                self.skipTest("O sistema não oferece suporte a links simbólicos.")
            except OSError as exc:
                if getattr(exc, "winerror", None) == 1314 or exc.errno in (
                    errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP,
                ):
                    self.skipTest("Link simbólico indisponível sem privilégios adicionais neste sistema.")
                raise
            with override_settings(PRIVATE_FILES_ROOT=alias / "anexos", MEDIA_ROOT=publico):
                with self.assertRaises(ImproperlyConfigured):
                    private_root()
                self.assertEqual(check_private_storage(None)[0].id, "clientes.E001")

    def test_isolamento_de_upload_e_csrf(self):
        for projeto in (self.oculta, self.alheia):
            response = self.client.post(self.endpoint("enviar_arquivo", projeto), {"anexo-titulo": "Documento", "anexo-arquivo": self.upload()})
            self.assertEqual(response.status_code, 404)
        self.assertFalse(ArquivoSolicitacao.objects.exists())
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.dono)
        self.assertEqual(protegido.post(self.endpoint("enviar_arquivo"), {}).status_code, 403)
        self.assertEqual(self.client.get(self.endpoint("enviar_arquivo")).status_code, 405)
        self.assertEqual(self.client.post(self.download_url(self.arquivo())).status_code, 405)

    def test_interface_vazia_paginacao_e_texto_escapado(self):
        response = self.client.get(self.projeto.get_absolute_url())
        self.assertContains(response, "Seus arquivos ficarão aqui.")
        self.arquivo(titulo="Arquivo oculto", visivel_cliente=False)
        self.arquivo(titulo="Documento alheio", solicitacao=self.alheia)
        for i in range(11):
            self.arquivo(titulo=f"<script>documento {i}</script>")
        response = self.client.get(self.projeto.get_absolute_url())
        self.assertEqual(len(response.context["arquivos_pagina"]), 10)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>documento")
        self.assertNotContains(response, "Arquivo oculto")
        self.assertNotContains(response, "Documento alheio")
        response = self.client.get(self.projeto.get_absolute_url(), {"arquivos": 2})
        self.assertEqual(len(response.context["arquivos_pagina"]), 1)
        self.assertEqual(self.client.get(self.projeto.get_absolute_url(), {"arquivos": "inválida"}).status_code, 200)
