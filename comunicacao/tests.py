import re
import tempfile
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.admin.models import LogEntry
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.acesso import token_acesso
from clientes.models import Solicitacao, AtualizacaoSolicitacao, MensagemSolicitacao, ArquivoSolicitacao
from clientes.services import salvar_atendimento
from painel.forms import ClienteCriarForm, ClienteEditarForm
from .models import EntregaEmail
from .services import solicitar_acesso, processar_entrega, notificar_evento


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   SITE_URL="https://portfolio.example", EMAIL_EQUIPE="equipe@example.com",
                   EMAIL_ENVIO_IMEDIATO=False, EMAIL_NOTIFICACOES_ATIVAS=True,
                   MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
class EmailsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser(username="gestor", password="SenhaForte982!")
        cls.cliente = User.objects.create_user(username="cliente", email="cliente@example.com", password="SenhaForte982!", first_name="Ana")
        cls.projeto = Solicitacao.objects.create(cliente=cls.cliente, titulo="Projeto reservado", descricao="Escopo reservado", visivel_cliente=True)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.admin)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings = override_settings(PRIVATE_FILES_ROOT=temp.name)
        settings.enable()
        self.addCleanup(settings.disable)
        mail.outbox = []

    def url(self, name, *args):
        return reverse(name, args=args)

    def link(self, index=-1):
        return re.search(r'https://portfolio\.example/area-cliente/definir-senha/[^\s]+', mail.outbox[index].body).group(0)

    def novo_convite(self):
        response = self.client.post(self.url("painel:cliente_novo"), {
            "username": "novo", "email": "novo@example.com", "first_name": "Novo",
            "modo_acesso": "convite", "is_staff": "on", "is_superuser": "on",
            "password1": "senha-forjada", "password2": "senha-forjada"})
        self.assertEqual(response.status_code, 302)
        return get_user_model().objects.get(username="novo"), EntregaEmail.objects.get(tipo="acesso")

    def msg(self, origem="equipe"):
        return MensagemSolicitacao.objects.create(solicitacao=self.projeto, autor=self.admin if origem == "equipe" else self.cliente, origem=origem, texto="CONTEUDO_PRIVADO_NAO_EMAIL")

    def test_convite_cria_cliente_sem_senha_ou_privilegios(self):
        user, entrega = self.novo_convite()
        self.assertTrue(user.acesso_pendente)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(entrega.estado, "pendente")
        self.assertFalse(self.client.login(username="novo", password="senha-forjada"))
        self.assertNotIn("senha-forjada", str(list(LogEntry.objects.values_list("change_message", flat=True))))
        self.assertTrue(processar_entrega(entrega.pk))
        self.assertEqual(mail.outbox[0].to, ["novo@example.com"])
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        self.assertIn("Seu usuário: novo", mail.outbox[0].body)

    def test_convite_define_senha_login_e_invalida_link(self):
        user, entrega = self.novo_convite()
        processar_entrega(entrega.pk)
        url = urlsplit(self.link()).path
        visitor = Client()
        response = visitor.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("set-password", response.url)
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertContains(visitor.get(response.url), "Defina sua senha")
        saved = visitor.post(response.url, {"new_password1": "UmaSenhaForte924!", "new_password2": "UmaSenhaForte924!"})
        self.assertRedirects(saved, self.url("area_cliente:acesso_definido"))
        user.refresh_from_db()
        self.assertFalse(user.acesso_pendente)
        self.assertTrue(user.check_password("UmaSenhaForte924!"))
        self.assertNotIn("_auth_user_id", visitor.session)
        self.assertContains(visitor.get(url), "Link indisponível")
        self.assertTrue(visitor.login(username="novo", password="UmaSenhaForte924!"))

    def test_recuperacao_ativa_conta_existente_e_invalida_sessao(self):
        customer = Client()
        customer.force_login(self.cliente)
        row = solicitar_acesso(self.cliente)
        processar_entrega(row.pk)
        visitor = Client()
        response = visitor.get(urlsplit(self.link()).path)
        visitor.post(response.url, {"new_password1": "OutraSenhaForte582!", "new_password2": "OutraSenhaForte582!"})
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.check_password("OutraSenhaForte582!"))
        self.assertEqual(customer.get(self.url("area_cliente:painel")).status_code, 302)

    def test_senha_fraca_ou_divergente_nao_consume_convite(self):
        user, entrega = self.novo_convite()
        processar_entrega(entrega.pk)
        visitor = Client()
        url = visitor.get(urlsplit(self.link()).path).url
        for senha, confirmacao in [("123", "123"), ("SenhaLonga291!", "Diferente982!")]:
            response = visitor.post(url, {"new_password1": senha, "new_password2": confirmacao})
            self.assertTrue(response.context["form"].errors)
        user.refresh_from_db()
        self.assertTrue(user.acesso_pendente)
        self.assertFalse(user.has_usable_password())

    def test_reenvio_exige_post_e_invalida_link_anterior(self):
        user, entrega = self.novo_convite()
        processar_entrega(entrega.pk)
        antigo = self.link()
        count = EntregaEmail.objects.count()
        url = self.url("painel:cliente_convite", user.pk)
        self.assertContains(self.client.get(url), user.email)
        self.assertEqual(EntregaEmail.objects.count(), count)
        self.client.post(url)
        processar_entrega(EntregaEmail.objects.latest("pk").pk)
        self.assertContains(Client().get(urlsplit(antigo).path), "Link indisponível")
        self.assertEqual(Client().get(urlsplit(self.link()).path).status_code, 302)

    def test_token_expirado_alterado_suspenso_email_alterado(self):
        token = token_acesso.make_token(self.cliente)
        self.assertFalse(token_acesso.check_token(self.cliente, token + "0"))
        with patch.object(token_acesso, "_now", return_value=token_acesso._now() + timedelta(hours=25)):
            self.assertFalse(token_acesso.check_token(self.cliente, token))
        self.cliente.is_active = False
        self.cliente.save(update_fields=["is_active"])
        self.cliente.is_active = True
        self.cliente.save(update_fields=["is_active"])
        self.assertFalse(token_acesso.check_token(self.cliente, token))
        token = token_acesso.make_token(self.cliente)
        self.cliente.email = "outro@example.com"
        self.cliente.save(update_fields=["email"])
        self.assertFalse(token_acesso.check_token(self.cliente, token))

    def test_recuperacao_resposta_generica_sem_enumerar_contas(self):
        User = get_user_model()
        User.objects.create_user(username="suspenso", email="suspenso@example.com", is_active=False)
        User.objects.create_user(username="externo", email="externo@example.com", password=None)
        User.objects.create_user(username="equipe", email="staff@example.com", password="Senha987!", is_staff=True)
        a = User.objects.create_user(username="duplo1", email="duplo@example.com", password="Senha987!")
        User.objects.create_user(username="duplo2", email="DUPLO@example.com", password="Senha987!")
        self.client.logout()
        for email in ["inexistente@example.com", "suspenso@example.com", "externo@example.com", "staff@example.com", a.email, self.cliente.email]:
            cache.clear()
            response = self.client.post(self.url("area_cliente:recuperar_acesso"), {"email": email})
            self.assertRedirects(response, self.url("area_cliente:recuperacao_solicitada"))
        self.assertEqual(EntregaEmail.objects.count(), 1)
        self.assertEqual(EntregaEmail.objects.get().cliente_id, self.cliente.pk)

    def test_recuperacao_pendente_e_limites_por_email_e_ip(self):
        user, entrega = self.novo_convite()
        EntregaEmail.objects.all().delete()
        self.client.logout()
        for _ in range(3):
            self.client.post(self.url("area_cliente:recuperar_acesso"), {"email": user.email})
        self.assertEqual(EntregaEmail.objects.count(), 1)
        self.assertEqual(EntregaEmail.objects.get().tipo, "acesso")
        for i in range(8):
            u = get_user_model().objects.create_user(username=f"u{i}", email=f"u{i}@example.com", password="Teste789!")
            self.client.post(self.url("area_cliente:recuperar_acesso"), {"email": u.email})
        self.assertEqual(EntregaEmail.objects.count(), 3)  # IP: 5 tentativas totais/minuto, inclusive as limitadas por e-mail.

    def test_email_duplicado_e_manual_com_senha_fraca_rejeitados(self):
        for email in ["CLIENTE@example.com", " cliente@example.com "]:
            form = ClienteCriarForm(data={"username": "novo", "email": email, "modo_acesso": "convite"})
            self.assertFalse(form.is_valid())
            self.assertIn("email", form.errors)
        form = ClienteCriarForm(data={"username": "novo", "modo_acesso": "manual", "password1": "123", "password2": "123"})
        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)
        other = get_user_model().objects.create_user(username="other", email="other@example.com")
        form = ClienteEditarForm(instance=other, data={"username": "other", "email": self.cliente.email, "is_active": "on"})
        self.assertFalse(form.is_valid())

    def test_links_usam_origem_configurada_nunca_host_da_requisicao(self):
        self.client.logout()
        with override_settings(ALLOWED_HOSTS=["host-injetado.example"]):
            self.client.post(self.url("area_cliente:recuperar_acesso"), {"email": self.cliente.email}, HTTP_HOST="host-injetado.example")
        processar_entrega(EntregaEmail.objects.get().pk)
        self.assertIn("https://portfolio.example/", mail.outbox[0].body)
        self.assertNotIn("host-injetado", mail.outbox[0].body)

    def test_csrf_e_permissoes_dos_envios(self):
        row = solicitar_acesso(self.cliente)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(self.url("painel:cliente_convite", self.cliente.pk)).status_code, 403)
        self.assertEqual(csrf.post(self.url("painel:email_repetir", row.pk)).status_code, 403)
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url("area_cliente:recuperar_acesso"), {"email": self.cliente.email}).status_code, 403)
        self.assertEqual(self.client.get(self.url("painel:email_repetir", row.pk)).status_code, 405)
        staff = get_user_model().objects.create_user(username="staff", is_staff=True)
        for user in [self.cliente, staff]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url("painel:emails")).status_code, 403)
            self.assertEqual(self.client.post(self.url("painel:cliente_convite", self.cliente.pk)).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url("painel:cliente_convite", self.admin.pk)).status_code, 404)

    def test_promover_usuario_invalida_acesso_de_cliente(self):
        token = token_acesso.make_token(self.cliente)
        self.cliente.user_permissions.add(Permission.objects.get(codename="view_user"))
        self.assertFalse(token_acesso.check_token(self.cliente, token))

    def test_atualizacao_publica_notifica_sem_conteudo_privado(self):
        atualizacao = AtualizacaoSolicitacao.objects.create(solicitacao=self.projeto, titulo="TITULO_RESERVADO", mensagem="TEXTO_RESERVADO")
        row = EntregaEmail.objects.get()
        self.assertEqual(row.tipo, "atualizacao")
        self.assertTrue(processar_entrega(row.pk))
        body = mail.outbox[0].body
        self.assertNotIn("RESERVADO", body)
        self.assertNotIn(self.projeto.titulo, body)
        self.assertIn(self.projeto.get_absolute_url(), body)
        atualizacao.mensagem = "Modificada"
        atualizacao.save()
        self.assertEqual(EntregaEmail.objects.count(), 1)

    def test_mensagem_e_arquivo_notificam_destinatario_correto(self):
        equipe_msg = self.msg()
        cliente_msg = self.msg("cliente")
        arquivo = ArquivoSolicitacao.objects.create(solicitacao=self.projeto, titulo="Anexo", arquivo=SimpleUploadedFile("teste.txt", b"CONTEUDO_PRIVADO"), origem="equipe")
        for row in EntregaEmail.objects.order_by("pk"):
            processar_entrega(row.pk)
        self.assertEqual([msg.to for msg in mail.outbox], [[self.cliente.email], ["equipe@example.com"], [self.cliente.email]])
        self.assertIn("/painel/atendimentos/", mail.outbox[1].body)
        self.assertTrue(all("CONTEUDO_PRIVADO" not in msg.body and not msg.attachments for msg in mail.outbox))

    def test_eventos_internos_e_cliente_sem_acesso_nao_geram_emails(self):
        AtualizacaoSolicitacao.objects.create(solicitacao=self.projeto, titulo="Interna", visivel_cliente=False)
        ArquivoSolicitacao.objects.create(solicitacao=self.projeto, titulo="Interno", arquivo=SimpleUploadedFile("t.txt", b"t"), visivel_cliente=False)
        self.assertFalse(EntregaEmail.objects.exists())
        self.projeto.visivel_cliente = False
        self.projeto.save()
        self.msg()
        self.assertFalse(EntregaEmail.objects.exists())
        self.projeto.visivel_cliente = True
        self.projeto.save()
        self.cliente.acesso_pendente = True
        self.cliente.save()
        self.msg()
        self.assertFalse(EntregaEmail.objects.exists())

    def test_revalida_visibilidade_e_destinatario_antes_de_enviar(self):
        msg = self.msg()
        self.cliente.email = "novo-email@example.com"
        self.cliente.save()
        row = EntregaEmail.objects.get()
        self.assertFalse(processar_entrega(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.estado, "cancelado")
        self.msg()
        row = EntregaEmail.objects.latest("pk")
        self.projeto.visivel_cliente = False
        self.projeto.save()
        self.assertFalse(processar_entrega(row.pk))
        self.assertFalse(mail.outbox)

    def test_arquivo_removido_ou_oculto_cancela_aviso(self):
        arquivo = ArquivoSolicitacao.objects.create(solicitacao=self.projeto, titulo="Arquivo", arquivo=SimpleUploadedFile("t.txt", b"t"))
        row = EntregaEmail.objects.get()
        arquivo.visivel_cliente = False
        arquivo.save()
        self.assertFalse(processar_entrega(row.pk))
        outro = ArquivoSolicitacao.objects.create(solicitacao=self.projeto, titulo="Outro", arquivo=SimpleUploadedFile("outro.txt", b"t"))
        row = EntregaEmail.objects.latest("pk")
        outro.delete()
        self.assertFalse(processar_entrega(row.pk))
        self.assertFalse(mail.outbox)

    def test_fila_revoga_recuperacao_ao_alterar_senha(self):
        row = solicitar_acesso(self.cliente)
        self.cliente.set_password("SenhaMudada627!")
        self.cliente.save(update_fields=["password"])
        self.assertFalse(processar_entrega(row.pk))
        self.assertFalse(mail.outbox)

    def test_falha_nao_desfaz_atendimento_e_pode_repetir(self):
        with self.assertLogs("comunicacao.services", level="WARNING"), override_settings(EMAIL_ENVIO_IMEDIATO=True), patch("comunicacao.services.EmailMultiAlternatives.send", side_effect=OSError("segredo-na-excecao")):
            with self.captureOnCommitCallbacks(execute=True):
                self.msg()
        self.assertEqual(MensagemSolicitacao.objects.count(), 1)
        row = EntregaEmail.objects.get()
        self.assertEqual(row.estado, "falha")
        self.assertNotIn("segredo", row.resultado)
        self.client.post(self.url("painel:email_repetir", row.pk))
        row.refresh_from_db()
        self.assertEqual(row.estado, "simulado")
        self.assertEqual(row.tentativas, 2)
        self.assertEqual(len(mail.outbox), 1)

    def test_envio_somente_apos_commit_e_sem_duplicidade(self):
        with override_settings(EMAIL_ENVIO_IMEDIATO=True), self.captureOnCommitCallbacks(execute=True):
            msg = self.msg()
            self.assertFalse(mail.outbox)
        self.assertEqual(len(mail.outbox), 1)
        row = EntregaEmail.objects.get()
        self.assertFalse(processar_entrega(row.pk))
        notificar_evento(msg, "mensagem")
        self.assertEqual(EntregaEmail.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_rollback_nao_cria_envio(self):
        with override_settings(EMAIL_ENVIO_IMEDIATO=True), self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.msg()
                    raise ValueError("rollback")
            except ValueError:
                pass
        self.assertFalse(EntregaEmail.objects.exists())
        self.assertFalse(mail.outbox)

    def test_historico_automatico_do_painel_gera_aviso(self):
        anterior = Solicitacao.objects.get(pk=self.projeto.pk)
        self.projeto.status = "andamento"
        self.projeto.progresso = 20
        salvar_atendimento(self.projeto, self.admin, anterior)
        self.assertEqual(EntregaEmail.objects.get().tipo, "atualizacao")

    def test_comando_processa_fila_sem_reenviar_concluidos(self):
        self.msg()
        self.msg("cliente")
        saida = StringIO()
        call_command("processar_emails", stdout=saida)
        self.assertEqual(len(mail.outbox), 2)
        call_command("processar_emails", repetir_falhas=True, stdout=saida)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Processados: 2", saida.getvalue())

    def test_desativar_notificacoes_e_email_equipe_vazio(self):
        with override_settings(EMAIL_NOTIFICACOES_ATIVAS=False):
            self.msg()
        with override_settings(EMAIL_EQUIPE=""):
            self.msg("cliente")
        self.assertFalse(EntregaEmail.objects.exists())
        self.assertIsNotNone(solicitar_acesso(self.cliente))

    def test_paginas_emails_estado_e_privacidade_de_tokens(self):
        row = solicitar_acesso(self.cliente)
        processar_entrega(row.pk)
        response = self.client.get(self.url("painel:emails"))
        self.assertContains(response, "Simulado — sem envio real")
        self.assertContains(response, "Modo de desenvolvimento")
        self.assertNotContains(response, self.link())
        self.assertIn("no-store", response["Cache-Control"])
        for name in ["area_cliente:recuperar_acesso", "area_cliente:recuperacao_solicitada", "area_cliente:acesso_definido"]:
            self.assertEqual(Client().get(self.url(name)).status_code, 200)
        self.assertContains(self.client.get(self.url("painel:cliente", self.cliente.pk)), "E-mails de acesso")

    def test_publicar_atendimento_e_anexo_dispara_aviso_uma_vez(self):
        self.projeto.visivel_cliente = False
        self.projeto.save()
        anterior = Solicitacao.objects.get(pk=self.projeto.pk)
        self.projeto.visivel_cliente = True
        salvar_atendimento(self.projeto, self.admin, anterior)
        self.assertEqual(EntregaEmail.objects.get().tipo, "atualizacao")
        arquivo = ArquivoSolicitacao.objects.create(solicitacao=self.projeto, titulo="Arquivo", arquivo=SimpleUploadedFile("arquivo.txt", b"t"), visivel_cliente=False)
        self.assertEqual(EntregaEmail.objects.count(), 1)
        arquivo.visivel_cliente = True
        arquivo.save()
        self.assertEqual(EntregaEmail.objects.count(), 2)
        arquivo.save()
        self.assertEqual(EntregaEmail.objects.count(), 2)

    def test_validacao_de_origem_e_smtp(self):
        from django.core.exceptions import ImproperlyConfigured
        from .checks import configuracao_email
        from .services import url_site
        for base in ["javascript:alert(1)", "https://user:pass@example.com", "https://example.com/path", "https://example.com/?host=evil"]:
            with override_settings(SITE_URL=base):
                with self.assertRaises(ImproperlyConfigured):
                    url_site("/")
        with override_settings(SMTP_USE_TLS=True, SMTP_USE_SSL=True):
            self.assertIn("comunicacao.E002", [x.id for x in configuracao_email(None)])

    def test_backend_smtp_recebe_configuracao_sem_envio_real(self):
        smtp = {"default": {"BACKEND": "django.core.mail.backends.smtp.EmailBackend", "OPTIONS": {
            "host": "smtp.example.com", "port": 587, "username": "usuario", "password": "somente-teste",
            "use_tls": True, "use_ssl": False, "timeout": 10}}}
        with override_settings(MAILERS=smtp), patch("django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1) as send:
            row = solicitar_acesso(self.cliente)
            self.assertTrue(processar_entrega(row.pk))
            row.refresh_from_db()
            self.assertEqual(row.estado, "enviado")
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args[0][0][0].to, [self.cliente.email])

    def test_link_literal_do_console_funciona_em_sessao_anonima(self):
        from contextlib import redirect_stdout
        console = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
        for convite in [True, False]:
            with self.subTest(convite=convite):
                if convite:
                    user, entrega = self.novo_convite()
                else:
                    user = self.cliente
                    entrega = solicitar_acesso(user)
                output = StringIO()
                with override_settings(MAILERS=console), redirect_stdout(output):
                    self.assertTrue(processar_entrega(entrega.pk))
                texto = output.getvalue()
                self.assertIn("Content-Transfer-Encoding: quoted-printable", texto)
                # Reproduz a cópia da saída literal, sem decodificar o MIME.
                link = texto.split("LINK DE ACESSO PARA TESTE LOCAL - COPIE A URL COMPLETA:\n")[1].splitlines()[0]
                self.assertNotIn("=", link)
                self.assertTrue(link.endswith("/"))
                visitor = Client()
                response = visitor.get(urlsplit(link).path, follow=True)
                self.assertTrue(response.context["validlink"])
                saved = visitor.post(response.request["PATH_INFO"], {
                    "new_password1": "SenhaDoConsole746!", "new_password2": "SenhaDoConsole746!"})
                self.assertRedirects(saved, self.url("area_cliente:acesso_definido"))
                user.refresh_from_db()
                self.assertTrue(user.check_password("SenhaDoConsole746!"))
                self.assertContains(Client().get(urlsplit(link).path), "Link indisponível")

    def test_smtp_nao_exibe_link_no_terminal(self):
        from contextlib import redirect_stdout
        smtp = {"default": {"BACKEND": "django.core.mail.backends.smtp.EmailBackend", "OPTIONS": {"host": "smtp.example.com"}}}
        output = StringIO()
        with override_settings(MAILERS=smtp), patch("django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1), redirect_stdout(output):
            self.assertTrue(processar_entrega(solicitar_acesso(self.cliente).pk))
        self.assertEqual(output.getvalue(), "")
