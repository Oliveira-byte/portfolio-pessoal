import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import ArquivoSolicitacao, AtualizacaoSolicitacao, MensagemSolicitacao, Origem, Solicitacao


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MensagensTests(TestCase):
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


    def mensagem(self, **kwargs):
        dados = dict(solicitacao=self.projeto, texto="Vamos revisar a primeira entrega?", autor=self.admin, origem=Origem.EQUIPE)
        dados.update(kwargs)
        return MensagemSolicitacao.objects.create(**dados)


    def endpoint(self, nome, projeto=None):
        return reverse("area_cliente:" + nome, args=[(projeto or self.projeto).pk])


    def download_url(self, arquivo, projeto=None):
        return reverse("area_cliente:arquivo_download", args=[(projeto or self.projeto).pk, arquivo.pk])


    def test_posts_em_contrato_alheio_ou_oculto_nao_gravam(self):
        for projeto in (self.alheia, self.oculta):
            self.assertEqual(self.client.post(self.endpoint("enviar_mensagem", projeto), {"conversa-texto": "Texto"}).status_code, 404)
            self.assertEqual(self.client.post(self.endpoint("enviar_arquivo", projeto), {"anexo-titulo": "Doc", "anexo-arquivo": self.upload()}).status_code, 404)
        self.assertFalse(MensagemSolicitacao.objects.exists())
        self.assertFalse(ArquivoSolicitacao.objects.exists())


    def test_csrf_e_metodos_http(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.dono)
        for nome in ("enviar_mensagem", "enviar_arquivo"):
            self.assertEqual(protegido.post(self.endpoint(nome), {}).status_code, 403)
            self.assertEqual(self.client.get(self.endpoint(nome)).status_code, 405)
        self.assertEqual(self.client.post(self.download_url(self.arquivo())).status_code, 405)


    def test_mensagem_ignora_identidade_forjada_e_nao_muda_progresso(self):
        response = self.client.post(self.endpoint("enviar_mensagem"), {
            "conversa-texto": "  Seguem minhas observações.  ", "autor": self.admin.pk,
            "origem": "equipe", "solicitacao": self.alheia.pk, "progresso": 100,
        })
        self.assertRedirects(response, self.projeto.get_absolute_url() + "#mensagens")
        mensagem = MensagemSolicitacao.objects.get()
        self.assertEqual(mensagem.autor, self.dono)
        self.assertEqual(mensagem.origem, Origem.CLIENTE)
        self.assertEqual(mensagem.solicitacao, self.projeto)
        self.assertEqual(mensagem.texto, "Seguem minhas observações.")
        self.assertIsNone(mensagem.lida_equipe_em)
        self.projeto.refresh_from_db()
        self.assertEqual(self.projeto.progresso, 25)


    def test_mensagem_vazia_ou_longa_rejeitada_sem_marcar_leitura(self):
        mensagem = self.mensagem()
        for texto in ("  \n ", "a" * 5001):
            response = self.client.post(self.endpoint("enviar_mensagem"), {"conversa-texto": texto})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(MensagemSolicitacao.objects.count(), 1)
        mensagem.refresh_from_db()
        self.assertIsNone(mensagem.lida_cliente_em)


    def test_textos_e_nomes_sao_escapados_e_notas_privadas_nao_aparecem(self):
        self.mensagem(texto='<script>alert("mensagem")</script>')
        self.arquivo(titulo='<script>alert("titulo")</script>')
        self.arquivo(titulo="Anexo interno", visivel_cliente=False)
        self.mensagem(solicitacao=self.alheia, texto="Conversa alheia")
        response = self.client.get(self.projeto.get_absolute_url())
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(")
        self.assertNotContains(response, "Anexo interno")
        self.assertNotContains(response, "Conversa alheia")


    def test_painel_conta_sem_duplicar_join_e_nao_marca_como_lidas(self):
        self.mensagem()
        self.mensagem()
        self.mensagem(origem=Origem.CLIENTE, autor=self.dono)
        self.mensagem(solicitacao=self.oculta)
        self.mensagem(solicitacao=self.alheia)
        for i in range(3):
            AtualizacaoSolicitacao.objects.create(solicitacao=self.projeto, titulo=f"Entrega {i}")
        response = self.client.get(reverse("area_cliente:painel"))
        self.assertEqual(response.context["total_novas_mensagens"], 2)
        self.assertEqual(response.context["solicitacoes_ativas"][0].novas_mensagens, 2)
        self.assertContains(response, "2 mensagens novas")
        self.assertFalse(MensagemSolicitacao.objects.filter(lida_cliente_em__isnull=False).exists())
        self.client.get(self.projeto.get_absolute_url())
        response = self.client.get(reverse("area_cliente:painel"))
        self.assertEqual(response.context["total_novas_mensagens"], 0)
        self.assertEqual(MensagemSolicitacao.objects.filter(lida_cliente_em__isnull=False).count(), 2)


    def test_paginacao_marca_apenas_mensagens_realmente_renderizadas(self):
        antigas = [self.mensagem(texto=f"Mensagem {i}") for i in range(32)]
        response = self.client.get(self.projeto.get_absolute_url())
        self.assertEqual(len(response.context["conversa"]), 30)
        self.assertEqual(response.context["conversa"][0].pk, antigas[2].pk)
        self.assertEqual(MensagemSolicitacao.objects.filter(lida_cliente_em__isnull=True).count(), 2)
        self.client.get(self.projeto.get_absolute_url(), {"conversa": 2})
        self.assertFalse(MensagemSolicitacao.objects.filter(lida_cliente_em__isnull=True).exists())
        self.assertEqual(self.client.get(self.projeto.get_absolute_url(), {"conversa": "inválida"}).status_code, 200)


    def test_admin_responde_com_identidade_equipe_e_impede_edicao_da_mensagem(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:clientes_mensagemsolicitacao_add"), {
            "solicitacao": self.projeto.pk, "texto": "Obrigada pelas referências.", "origem": "cliente", "autor": self.dono.pk,
        })
        self.assertEqual(response.status_code, 302)
        mensagem = MensagemSolicitacao.objects.get()
        self.assertEqual(mensagem.origem, Origem.EQUIPE)
        self.assertEqual(mensagem.autor, self.admin)
        response = self.client.post(reverse("admin:clientes_mensagemsolicitacao_change", args=[mensagem.pk]), {"texto": "Texto adulterado", "solicitacao": self.alheia.pk})
        self.assertEqual(response.status_code, 302)
        mensagem.refresh_from_db()
        self.assertEqual(mensagem.texto, "Obrigada pelas referências.")
        self.assertEqual(mensagem.solicitacao, self.projeto)


    def test_admin_listagem_nao_marca_leitura_mas_abrir_mensagem_marca(self):
        mensagem = self.mensagem(origem=Origem.CLIENTE, autor=self.dono)
        outra = self.mensagem(origem=Origem.CLIENTE, autor=self.dono)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("admin:clientes_solicitacao_changelist")), "leitura=novas")
        self.assertContains(self.client.get(reverse("admin:clientes_solicitacao_change", args=[self.projeto.pk])), "Enviar mensagem")
        self.assertContains(self.client.get(reverse("admin:clientes_mensagemsolicitacao_changelist"), {"leitura": "novas"}), "Nova do cliente")
        mensagem.refresh_from_db()
        self.assertIsNone(mensagem.lida_equipe_em)
        response = self.client.get(reverse("admin:clientes_mensagemsolicitacao_change", args=[mensagem.pk]))
        self.assertContains(response, "Enviar resposta nesta contratação")
        mensagem.refresh_from_db()
        outra.refresh_from_db()
        self.assertIsNotNone(mensagem.lida_equipe_em)
        self.assertIsNone(outra.lida_equipe_em)
        self.client.force_login(self.dono)
        self.assertContains(self.client.get(self.projeto.get_absolute_url()), "Lida pela equipe em")


    def test_admin_acao_leitura_nao_marca_mensagem_da_equipe(self):
        cliente = self.mensagem(origem=Origem.CLIENTE, autor=self.dono)
        equipe = self.mensagem()
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:clientes_mensagemsolicitacao_changelist"), {"action": "marcar_lidas", "_selected_action": [cliente.pk, equipe.pk]})
        self.assertEqual(response.status_code, 302)
        cliente.refresh_from_db()
        equipe.refresh_from_db()
        self.assertIsNotNone(cliente.lida_equipe_em)
        self.assertIsNone(equipe.lida_equipe_em)
