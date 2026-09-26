from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AtualizacaoSolicitacao, Solicitacao


class AcompanhamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.dono = User.objects.create_user(username="cliente_a", password="SenhaTeste!987")
        cls.outro = User.objects.create_user(username="cliente_b", password="SenhaTeste!987")
        cls.admin = User.objects.create_superuser(username="admin", password="SenhaTeste!987")
        cls.projeto = Solicitacao.objects.create(
            cliente=cls.dono, titulo="Site institucional", descricao="Escopo do site",
            status=Solicitacao.Status.ANDAMENTO, progresso=40, visivel_cliente=True,
        )
        cls.servico = Solicitacao.objects.create(
            cliente=cls.dono, titulo="Suporte contratado", descricao="Escopo do suporte", tipo="servico",
            status=Solicitacao.Status.AGUARDANDO, progresso=20,
            proximo_passo="Enviar os acessos solicitados pelo canal combinado.", visivel_cliente=True,
        )
        cls.concluida = Solicitacao.objects.create(
            cliente=cls.dono, titulo="Entrega finalizada", descricao="Concluída",
            status=Solicitacao.Status.CONCLUIDA, progresso=100, visivel_cliente=True,
        )
        cls.oculta = Solicitacao.objects.create(cliente=cls.dono, titulo="Rascunho privado", descricao="Oculto")
        cls.alheia = Solicitacao.objects.create(cliente=cls.outro, titulo="Outro contrato privado", descricao="Segredo", visivel_cliente=True)
        cls.publica = AtualizacaoSolicitacao.objects.create(solicitacao=cls.projeto, titulo="Layout aprovado", mensagem="Mensagem pública")
        cls.privada = AtualizacaoSolicitacao.objects.create(solicitacao=cls.projeto, titulo="Nota interna reservada", mensagem="Mensagem interna reservada", visivel_cliente=False)
        AtualizacaoSolicitacao.objects.create(solicitacao=cls.oculta, titulo="Histórico do rascunho")
        AtualizacaoSolicitacao.objects.create(solicitacao=cls.alheia, titulo="Histórico alheio")

    def setUp(self):
        self.client.force_login(self.dono)

    def test_painel_prioriza_andamento_e_calcula_resumo(self):
        response = self.client.get(reverse("area_cliente:painel"))
        self.assertContains(response, "Andamento das")
        self.assertEqual(response.context["total_ativas"], 2)
        self.assertEqual(response.context["total_aguardando"], 1)
        self.assertEqual(response.context["total_concluidas"], 1)
        self.assertEqual(response.context["solicitacoes_ativas"][0], self.servico)
        self.assertEqual(response.context["solicitacoes_encerradas"], [self.concluida])
        self.assertContains(response, 'value="40"')
        self.assertContains(response, "1 solicitação aguardando")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_lista_e_novidades_nao_vazam_contratos_ou_notas(self):
        response = self.client.get(reverse("area_cliente:painel"), {"cliente": self.outro.pk})
        for texto in ["Rascunho privado", "Outro contrato privado", "Nota interna reservada", "Histórico alheio", "Histórico do rascunho"]:
            self.assertNotContains(response, texto)
        self.assertContains(response, "Layout aprovado")
        item = next(item for item in response.context["solicitacoes_ativas"] if item.pk == self.projeto.pk)
        self.assertEqual(item.ultima_novidade, self.publica.criado_em)

    def test_detalhe_so_mostra_historico_publico_da_solicitacao(self):
        response = self.client.get(self.projeto.get_absolute_url())
        self.assertContains(response, "Escopo do site")
        self.assertContains(response, "Layout aprovado")
        self.assertNotContains(response, "Nota interna reservada")
        self.assertNotContains(response, "Histórico alheio")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_trocar_id_na_url_nao_da_acesso_a_outro_cliente(self):
        for projeto in [self.alheia, self.oculta]:
            with self.subTest(projeto=projeto):
                self.assertEqual(self.client.get(projeto.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse("area_cliente:solicitacao_detalhe", args=[999999])).status_code, 404)

    def test_staff_tambem_nao_tem_excecao_no_portal(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.projeto.get_absolute_url()).status_code, 404)

    def test_cliente_nao_pode_alterar_dados_por_post(self):
        response = self.client.post(self.projeto.get_absolute_url(), {"progresso": 100, "cliente": self.outro.pk})
        self.assertEqual(response.status_code, 405)
        self.projeto.refresh_from_db()
        self.assertEqual(self.projeto.progresso, 40)
        self.assertEqual(self.projeto.cliente_id, self.dono.pk)

    def test_visitante_vai_ao_login_e_cliente_nao_acessa_admin(self):
        response = self.client.get(reverse("admin:clientes_solicitacao_change", args=[self.projeto.pk]))
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        response = self.client.get(self.projeto.get_absolute_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("area_cliente:entrar"), response.url)

    def test_remover_visibilidade_revoga_acesso_imediatamente(self):
        self.projeto.visivel_cliente = False
        self.projeto.save()
        self.assertEqual(self.client.get(self.projeto.get_absolute_url()).status_code, 404)

    def test_estado_vazio_sem_metricas_ficticias(self):
        Solicitacao.objects.filter(cliente=self.dono).update(visivel_cliente=False)
        response = self.client.get(reverse("area_cliente:painel"))
        self.assertContains(response, "Suas solicitações aparecerão aqui.")
        self.assertNotContains(response, 'class="p6-summary"')

    def test_prazo_vencido_so_em_solicitacoes_nao_encerradas(self):
        ontem = timezone.localdate() - timedelta(days=1)
        self.projeto.prazo = ontem
        self.assertTrue(self.projeto.prazo_vencido)
        self.concluida.prazo = ontem
        self.assertFalse(self.concluida.prazo_vencido)
        self.projeto.prazo = timezone.localdate()
        self.assertFalse(self.projeto.prazo_vencido)

    def test_validacao_de_percentual_datas_e_pendencias(self):
        self.projeto.progresso = 101
        with self.assertRaises(ValidationError):
            self.projeto.full_clean()
        self.projeto.progresso = 40
        self.projeto.data_inicio = timezone.localdate()
        self.projeto.prazo = timezone.localdate() - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.projeto.full_clean()
        self.servico.proximo_passo = ""
        with self.assertRaises(ValidationError):
            self.servico.full_clean()

    def test_banco_impede_percentual_fora_do_intervalo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Solicitacao.objects.filter(pk=self.projeto.pk).update(progresso=150)

    def test_textos_sao_escapados(self):
        self.projeto.descricao = '<script>alert("teste")</script>'
        self.projeto.save()
        response = self.client.get(self.projeto.get_absolute_url())
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert(')

    def admin_payload(self, **updates):
        dados = {
            "cliente": self.dono.pk, "titulo": "Nova contratação", "tipo": "projeto",
            "descricao": "Escopo combinado", "status": "andamento", "progresso": 25,
            "proximo_passo": "Preparar primeira versão", "visivel_cliente": "on",
            "atualizacoes-TOTAL_FORMS": 0, "atualizacoes-INITIAL_FORMS": 0,
            "atualizacoes-MIN_NUM_FORMS": 0, "atualizacoes-MAX_NUM_FORMS": 1000,
            "_save": "Salvar",
        }
        dados.update(updates)
        return dados

    def test_admin_cadastra_e_registra_andamento_automaticamente(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:clientes_solicitacao_add"), self.admin_payload())
        self.assertEqual(response.status_code, 302)
        projeto = Solicitacao.objects.get(titulo="Nova contratação")
        primeira = projeto.atualizacoes.get()
        self.assertEqual(primeira.progresso_registrado, 25)
        self.assertEqual(primeira.autor, self.admin)
        # Mantém a atualização existente e acrescenta uma mensagem manual no mesmo formulário.
        dados = self.admin_payload(status="concluida", progresso=60, **{
            "atualizacoes-TOTAL_FORMS": 2, "atualizacoes-INITIAL_FORMS": 1,
            "atualizacoes-0-id": primeira.pk, "atualizacoes-0-titulo": primeira.titulo,
            "atualizacoes-0-mensagem": primeira.mensagem, "atualizacoes-0-visivel_cliente": "on",
            "atualizacoes-1-titulo": "Entrega aprovada", "atualizacoes-1-mensagem": "Concluímos a entrega.",
            "atualizacoes-1-visivel_cliente": "on",
        })
        response = self.client.post(reverse("admin:clientes_solicitacao_change", args=[projeto.pk]), dados)
        self.assertEqual(response.status_code, 302)
        projeto.refresh_from_db()
        self.assertEqual(projeto.progresso, 100)
        self.assertEqual(projeto.atualizacoes.count(), 3)
        self.assertEqual(projeto.atualizacoes.get(titulo="Andamento atualizado").progresso_registrado, 100)
        manual = projeto.atualizacoes.get(titulo="Entrega aprovada")
        self.assertEqual(manual.progresso_registrado, 100)
        self.assertEqual(manual.autor, self.admin)
