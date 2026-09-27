from datetime import timedelta
from pathlib import Path
import tempfile

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import Solicitacao, OrdemManutencao, AtualizacaoSolicitacao, MensagemSolicitacao, ArquivoSolicitacao, Origem
from core.models import ConfiguracaoContato
from portfolio.models import Projeto, Tecnologia


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PainelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser(username="gestor", password="SenhaForte987!")
        cls.staff = User.objects.create_user(username="equipe", password="SenhaForte987!", is_staff=True)
        cls.cliente = User.objects.create_user(username="cliente", password="SenhaForte987!", first_name="Cliente", email="cliente@example.com")
        cls.outro = User.objects.create_user(username="outro", password="SenhaForte987!")
        cls.projeto = Solicitacao.objects.create(cliente=cls.cliente, titulo="Projeto privado", descricao="Escopo combinado", status="andamento", progresso=30, visivel_cliente=True, prazo=timezone.localdate()-timedelta(days=1))
        cls.os = OrdemManutencao.objects.create(cliente=cls.outro, titulo="Manutenção reservada", descricao="Limpeza", equipamento="notebook", marca="Dell", modelo="Inspiron", relato_cliente="Aquecimento", etapa="diagnostico", anotacoes_internas="NOTA TECNICA RESERVADA", visivel_cliente=True)
        cls.msg = MensagemSolicitacao.objects.create(solicitacao=cls.projeto, autor=cls.cliente, origem=Origem.CLIENTE, texto="Pergunta nova")
        cls.msg_os = MensagemSolicitacao.objects.create(solicitacao=cls.os, autor=cls.outro, origem=Origem.CLIENTE, texto="Mensagem da manutenção")

    def setUp(self):
        self.client.force_login(self.admin)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        setting = override_settings(PRIVATE_FILES_ROOT=temp.name)
        setting.enable()
        self.addCleanup(setting.disable)

    def url(self, name, *args):
        return reverse("painel:"+name, args=args)

    def permitir(self, *codes):
        self.staff.user_permissions.add(*Permission.objects.filter(codename__in=codes))
        self.client.force_login(self.staff)

    def upload(self):
        return SimpleUploadedFile("entrega.txt", b"Conteudo privado")

    def arquivo(self, solicitacao=None):
        return ArquivoSolicitacao.objects.create(solicitacao=solicitacao or self.projeto, titulo="Entrega", arquivo=self.upload(), enviado_por=self.admin)

    def payload(self, **updates):
        data = {"cliente": self.cliente.pk, "tipo": "projeto", "titulo": "Projeto cadastrado", "descricao": "Escopo do novo projeto", "status": "andamento", "progresso": "35", "visivel_cliente": "on"}
        data.update(updates)
        return data

    def os_payload(self, **updates):
        data = {"cliente": self.cliente.pk, "titulo": "Nova ordem técnica", "descricao": "Revisão", "equipamento": "computador", "marca": "Montado", "modelo": "Desktop", "relato_cliente": "Lentidão", "etapa": "manutencao", "valor_pecas": "0", "valor_logistica": "0", "recebimento": "coleta", "devolucao": "entrega", "visivel_cliente": "on"}
        data.update(updates)
        return data

    def test_visitante_e_cliente_nao_acessam_painel(self):
        urls = [self.url("inicio"), self.url("clientes"), self.url("cliente", self.cliente.pk), self.url("cliente_novo"), self.url("atendimentos", "projetos"), self.url("atendimento", self.projeto.pk), self.url("atendimento_novo", "manutencoes"), self.url("mensagens"), self.url("arquivos"), self.url("portfolio"), self.url("contato")]
        self.client.logout()
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/painel/entrar/", response.url)
        self.client.force_login(self.cliente)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.url("enviar_mensagem", self.projeto.pk), {"mensagem-texto": "Forjada"}).status_code, 403)

    def test_login_exige_staff_e_rejeita_next_externo(self):
        self.client.logout()
        response = self.client.post(self.url("entrar"), {"username": "cliente", "password": "SenhaForte987!"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(self.url("entrar"), {"username": "gestor", "password": "SenhaForte987!", "next": "https://evil.example/"})
        self.assertRedirects(response, self.url("inicio"))
        self.assertEqual(self.client.get(self.url("sair")).status_code, 405)
        self.assertEqual(self.client.post(self.url("sair")).status_code, 302)

    def test_dashboard_exibe_dados_reais_e_nao_marca_mensagens(self):
        response = self.client.get(self.url("inicio"))
        self.assertEqual(response.context["abertos"], 2)
        self.assertEqual(response.context["novas"], 2)
        self.assertEqual(response.context["atrasados"], 1)
        self.assertIn("no-store", response["Cache-Control"])
        self.msg.refresh_from_db()
        self.assertIsNone(self.msg.lida_equipe_em)

    def test_staff_sem_permissao_nao_recebe_listas_notas_ou_metricas(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url("inicio"))
        self.assertEqual(response.context["abertos"], 0)
        self.assertIsNone(response.context["novas"])
        for text in ("Projeto privado", "Manutenção reservada", "Pergunta nova", "NOTA TECNICA RESERVADA"):
            self.assertNotContains(response, text)
        for name in ("clientes", "mensagens", "arquivos", "portfolio", "contato"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 403)

    def test_permissao_digital_nao_libera_manutencao_nem_mensagens_ou_arquivos_dela(self):
        arquivo = self.arquivo(self.os)
        self.permitir("view_solicitacao", "view_mensagemsolicitacao", "view_arquivosolicitacao")
        self.assertEqual(self.client.get(self.url("atendimento", self.os.pk)).status_code, 404)
        self.assertNotContains(self.client.get(self.url("mensagens")), "Mensagem da manutenção")
        self.assertEqual(self.client.get(self.url("arquivo_download", self.os.pk, arquivo.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("abrir_mensagem", self.msg_os.pk)).status_code, 404)
        self.assertContains(self.client.get(self.url("atendimento", self.projeto.pk)), "Projeto privado")
        self.assertEqual(self.client.post(self.url("atendimento_editar", self.projeto.pk), self.payload()).status_code, 403)
        self.assertEqual(self.client.post(self.url("enviar_mensagem", self.projeto.pk), {"mensagem-texto": "Teste"}).status_code, 403)

    def test_cadastrar_cliente_ignora_privilegios_forjados(self):
        response = self.client.post(self.url("cliente_novo"), {"username": "novo", "first_name": "Novo", "email": "novo@example.com", "password1": "OutraSenhaForte982!", "password2": "OutraSenhaForte982!", "is_staff": "on", "is_superuser": "on", "user_permissions": [1]})
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="novo")
        self.assertTrue(user.check_password("OutraSenhaForte982!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.user_permissions.exists())
        self.assertTrue(LogEntry.objects.filter(object_id=str(user.pk), action_flag=1).exists())

    def test_editar_cliente_suspende_acesso_e_preserva_historico(self):
        response = self.client.post(self.url("cliente_editar", self.cliente.pk), {"username": "cliente", "first_name": "Nome atualizado", "email": "novo@example.com", "is_staff": "on"})
        self.assertEqual(response.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.is_active)
        self.assertFalse(self.cliente.is_staff)
        self.assertEqual(self.cliente.solicitacoes.count(), 1)
        self.assertEqual(self.cliente.first_name, "Nome atualizado")

    def test_painel_clientes_nao_edita_equipe_nem_contas_com_permissoes(self):
        grupo = Group.objects.create(name="Permissoes reservadas")
        grupo.permissions.add(Permission.objects.get(codename="change_user"))
        self.outro.groups.add(grupo)
        for user in (self.admin, self.staff, self.outro):
            for name in ("cliente", "cliente_editar", "cliente_senha"):
                self.assertEqual(self.client.get(self.url(name, user.pk)).status_code, 404)
        response = self.client.get(self.url("clientes"))
        self.assertEqual(list(response.context["clientes"].object_list), [self.cliente])

    def test_senha_validada_e_sessao_antiga_invalidada(self):
        cliente_browser = Client()
        cliente_browser.force_login(self.cliente)
        response = self.client.post(self.url("cliente_senha", self.cliente.pk), {"new_password1": "123", "new_password2": "123"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(self.url("cliente_senha", self.cliente.pk), {"new_password1": "SenhaNovaCliente981!", "new_password2": "SenhaNovaCliente981!"})
        self.assertEqual(response.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.check_password("SenhaNovaCliente981!"))
        self.assertEqual(cliente_browser.get(reverse("area_cliente:painel")).status_code, 302)
        self.assertFalse(LogEntry.objects.filter(change_message__contains="SenhaNovaCliente981!").exists())

    def test_cadastro_digital_registra_historico_e_impede_tipo_manutencao(self):
        response = self.client.post(self.url("atendimento_novo", "projetos"), self.payload())
        self.assertEqual(response.status_code, 302)
        obj = Solicitacao.objects.get(titulo="Projeto cadastrado")
        self.assertEqual(obj.atualizacoes.get().autor, self.admin)
        self.assertEqual(obj.atualizacoes.get().progresso_registrado, 35)
        response = self.client.post(self.url("atendimento_novo", "projetos"), self.payload(tipo="manutencao"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Solicitacao.objects.filter(titulo="Projeto cadastrado").count(), 1)

    def test_edicao_nao_reassocia_cliente_e_conclusao_atualiza_historico(self):
        response = self.client.post(self.url("atendimento_editar", self.projeto.pk), self.payload(cliente=self.outro.pk, status="concluida", progresso="20"))
        self.assertEqual(response.status_code, 302)
        self.projeto.refresh_from_db()
        self.assertEqual(self.projeto.cliente_id, self.cliente.pk)
        self.assertEqual(self.projeto.progresso, 100)
        self.assertEqual(self.projeto.atualizacoes.get().titulo, "Andamento atualizado")

    def test_os_cadastrada_com_orcamento_notas_e_agendamento(self):
        response = self.client.post(self.url("atendimento_novo", "manutencoes"), self.os_payload(orcamento_acordado="on", valor_servicos="100.50", data_acordo=timezone.localdate().isoformat(), detalhes_orcamento="Limpeza combinada", anotacoes_internas="Nota só interna", coleta_prevista="2026-10-10T09:00", devolucao_prevista="2026-10-11T16:00"))
        self.assertEqual(response.status_code, 302)
        obj = OrdemManutencao.objects.get(titulo="Nova ordem técnica")
        self.assertEqual(str(obj.total_acordado), "100.50")
        self.assertEqual(obj.atualizacoes.count(), 2)
        self.assertEqual(timezone.localtime(obj.coleta_prevista).hour, 9)
        self.assertContains(self.client.get(self.url("atendimento", obj.pk)), "Nota só interna")
        self.client.force_login(self.cliente)
        self.assertNotContains(self.client.get(obj.get_absolute_url()), "Nota só interna")
        self.assertContains(self.client.get(obj.get_absolute_url()), "100,50")

    def test_os_invalida_nao_cria_registro_parcial(self):
        response = self.client.post(self.url("atendimento_novo", "manutencoes"), self.os_payload(orcamento_acordado="on"))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Solicitacao.objects.filter(titulo="Nova ordem técnica").exists())
        self.assertFalse(LogEntry.objects.exists())

    def test_cadastro_nao_vincula_conta_administrativa(self):
        response = self.client.post(self.url("atendimento_novo", "projetos"), self.payload(cliente=self.admin.pk))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Solicitacao.objects.filter(titulo="Projeto cadastrado").exists())

    def test_resposta_identidade_equipe_e_indicador_no_portal(self):
        response = self.client.post(self.url("enviar_mensagem", self.projeto.pk), {"mensagem-texto": "Resposta da equipe", "autor": self.cliente.pk, "origem": "cliente", "solicitacao": self.os.pk})
        self.assertEqual(response.status_code, 302)
        msg = self.projeto.mensagens.get(texto="Resposta da equipe")
        self.assertEqual(msg.origem, Origem.EQUIPE)
        self.assertEqual(msg.autor, self.admin)
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse("area_cliente:painel")).context["total_novas_mensagens"], 1)

    def test_mensagem_invalida_escapada_e_sem_leitura_na_renderizacao_de_erro(self):
        response = self.client.post(self.url("enviar_mensagem", self.projeto.pk), {"mensagem-texto": " "})
        self.assertEqual(response.status_code, 400)
        self.msg.refresh_from_db()
        self.assertIsNone(self.msg.lida_equipe_em)
        self.msg.texto = '<script>alert("x")</script>'
        self.msg.save()
        response = self.client.get(self.url("atendimento", self.projeto.pk))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert(')

    def test_caixa_nao_marca_leitura_e_link_abre_pagina_certa(self):
        for i in range(35):
            MensagemSolicitacao.objects.create(solicitacao=self.projeto, autor=self.cliente, origem=Origem.CLIENTE, texto=f"Mensagem {i}")
        self.client.get(self.url("mensagens"))
        self.msg.refresh_from_db()
        self.assertIsNone(self.msg.lida_equipe_em)
        response = self.client.get(self.url("abrir_mensagem", self.msg.pk))
        self.assertIn("conversa=2", response.url)
        response = self.client.get(response.url)
        self.assertContains(response, "Pergunta nova")
        self.assertEqual(self.projeto.mensagens.filter(lida_equipe_em__isnull=False).count(), 6)
        self.msg_os.refresh_from_db()
        self.assertIsNone(self.msg_os.lida_equipe_em)

    def test_upload_download_visibilidade_exclusao_com_confirmacao(self):
        response = self.client.post(self.url("enviar_arquivo", self.projeto.pk), {"arquivo-titulo": "Documento", "arquivo-arquivo": self.upload(), "arquivo-visivel_cliente": "on", "origem": "cliente", "enviado_por": self.cliente.pk})
        self.assertEqual(response.status_code, 302)
        obj = ArquivoSolicitacao.objects.get()
        self.assertEqual(obj.origem, Origem.EQUIPE)
        self.assertEqual(obj.enviado_por, self.admin)
        response = self.client.get(self.url("arquivo_download", self.projeto.pk, obj.pk))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(b"".join(response.streaming_content), b"Conteudo privado")
        response = self.client.post(self.url("arquivo_editar", self.projeto.pk, obj.pk), {"titulo": "Interno"})
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertFalse(obj.visivel_cliente)
        self.assertEqual(self.client.get(self.url("arquivo_download", self.os.pk, obj.pk)).status_code, 404)
        path = Path(obj.arquivo.path)
        url = self.url("arquivo_excluir", self.projeto.pk, obj.pk)
        self.assertContains(self.client.get(url), "Confirmar exclusão")
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(path.exists())
        self.assertFalse(ArquivoSolicitacao.objects.exists())
        self.assertTrue(LogEntry.objects.filter(action_flag=3).exists())

    def test_upload_rejeita_formato_e_atualizacao_interna_nao_vaza(self):
        response = self.client.post(self.url("enviar_arquivo", self.projeto.pk), {"arquivo-titulo": "Invalido", "arquivo-arquivo": SimpleUploadedFile("script.html", b"script")})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ArquivoSolicitacao.objects.exists())
        response = self.client.post(self.url("adicionar_atualizacao", self.projeto.pk), {"historico-titulo": "NOTA_INTERNA", "historico-mensagem": "Somente equipe"})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.cliente)
        self.assertNotContains(self.client.get(self.projeto.get_absolute_url()), "NOTA_INTERNA")

    def test_csrf_e_metodos_de_mutacao(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.admin)
        for name in ("enviar_mensagem", "enviar_arquivo", "adicionar_atualizacao"):
            url = self.url(name, self.projeto.pk)
            self.assertEqual(protegido.post(url, {}).status_code, 403)
            self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(protegido.post(self.url("cliente_novo"), {}).status_code, 403)
        arquivo = self.arquivo()
        self.assertEqual(protegido.post(self.url("arquivo_excluir", self.projeto.pk, arquivo.pk)).status_code, 403)
        self.assertTrue(ArquivoSolicitacao.objects.filter(pk=arquivo.pk).exists())

    def test_portfolio_tecnologias_e_contatos_no_painel(self):
        self.assertEqual(self.client.post(self.url("tecnologias"), {"nome": "Django"}).status_code, 302)
        tecnologia = Tecnologia.objects.get(nome="Django")
        dados = {"titulo": "Meu projeto", "slug": "meu-projeto", "resumo": "Resumo público", "descricao": "Descrição", "status": "desenvolvimento", "capa_estilo": "padrao", "ordem": "0", "tecnologias": [tecnologia.pk]}
        self.assertEqual(self.client.post(self.url("portfolio_novo"), dados).status_code, 302)
        projeto = Projeto.objects.get(slug="meu-projeto")
        self.assertEqual(self.client.get(projeto.get_absolute_url()).status_code, 404)
        dados["publicado"] = "on"
        self.assertEqual(self.client.post(self.url("portfolio_editar", projeto.pk), dados).status_code, 302)
        self.assertContains(self.client.get(projeto.get_absolute_url()), "Resumo público")
        self.assertEqual(projeto.tecnologias.count(), 1)
        self.assertEqual(self.client.post(self.url("contato"), {"email": "atendimento@example.com", "whatsapp": "5511999990000", "whatsapp_ativo": "on"}).status_code, 302)
        self.assertEqual(ConfiguracaoContato.objects.count(), 1)
        self.assertContains(self.client.get(reverse("core:contato")), "https://wa.me/5511999990000")

    def test_telas_renderizam_e_listas_aceitam_paginacao_e_filtros(self):
        arquivo = self.arquivo()
        urls = [self.url("cliente", self.cliente.pk), self.url("cliente_novo"), self.url("cliente_editar", self.cliente.pk), self.url("cliente_senha", self.cliente.pk), self.url("atendimentos", "manutencoes"), self.url("atendimento_novo", "manutencoes"), self.url("atendimento_editar", self.os.pk), self.url("atendimento", self.os.pk), self.url("arquivo_editar", self.projeto.pk, arquivo.pk), self.url("portfolio_novo"), self.url("tecnologias"), self.url("contato")]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response["Cache-Control"])
        response = self.client.get(self.url("atendimentos", "projetos"), {"situacao": "atrasados", "pagina": "invalida", "q": "Projeto"})
        self.assertContains(response, "Projeto privado")
        self.assertNotContains(response, "Manutenção reservada")
        for name in ("clientes", "mensagens", "arquivos", "portfolio"):
            self.assertEqual(self.client.get(self.url(name), {"pagina": "999", "q": "nada"}).status_code, 200)

    def test_cliente_vinculado_a_os_ve_somente_seus_atendimentos_no_portal(self):
        self.client.force_login(self.cliente)
        response = self.client.get(reverse("area_cliente:painel"))
        self.assertContains(response, "Projeto privado")
        self.assertNotContains(response, "Manutenção reservada")
        self.assertEqual(self.client.get(self.url("atendimento", self.projeto.pk)).status_code, 403)
