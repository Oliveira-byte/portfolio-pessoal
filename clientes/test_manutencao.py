from datetime import timedelta
from decimal import Decimal
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ArquivoSolicitacao, MensagemSolicitacao, OrdemManutencao, Solicitacao


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ManutencaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.cliente = User.objects.create_user(username="cliente_os")
        cls.outro = User.objects.create_user(username="outro_os")
        cls.admin = User.objects.create_superuser(username="admin_os", password="senha_teste")
        cls.os = OrdemManutencao.objects.create(
            cliente=cls.cliente, titulo="Revisão do notebook", descricao="Limpeza e diagnóstico",
            equipamento="notebook", marca="Dell", modelo="Inspiron", relato_cliente="Desliga durante o uso",
            anotacoes_internas="NOTA RESERVADA 9821", diagnostico_publico="Avaliação térmica em andamento",
            etapa="diagnostico", visivel_cliente=True, detalhes_orcamento="RASCUNHO RESERVADO 6543",
            valor_servicos=Decimal("150.25"), valor_pecas=Decimal("25.50"), valor_logistica=Decimal("20.00"),
            endereco_atendimento="ENDEREÇO PRIVADO 321", recebido_em=timezone.localdate(),
        )
        cls.digital = Solicitacao.objects.create(cliente=cls.cliente, titulo="Projeto web", descricao="Um site", progresso=40, visivel_cliente=True)

    def setUp(self):
        self.client.force_login(self.cliente)

    def payload(self, **updates):
        dados = {
            "cliente": self.cliente.pk, "titulo": "Manutenção cadastrada", "descricao": "Limpeza preventiva",
            "equipamento": "computador", "marca": "Montado", "modelo": "Desktop", "relato_cliente": "Ruído no equipamento",
            "etapa": "diagnostico", "visivel_cliente": "on", "valor_pecas": "0", "valor_logistica": "0",
            "recebimento": "coleta", "devolucao": "entrega",
            "atualizacoes-TOTAL_FORMS": "0", "atualizacoes-INITIAL_FORMS": "0",
            "atualizacoes-MIN_NUM_FORMS": "0", "atualizacoes-MAX_NUM_FORMS": "1000",
            "_save": "Salvar",
        }
        dados.update(updates)
        return dados

    def test_detalhe_mostra_etapa_e_nao_expoe_notas_ou_orcamento_em_negociacao(self):
        response = self.client.get(self.os.get_absolute_url())
        self.assertContains(response, "Em diagnóstico")
        self.assertContains(response, f"OS #{self.os.pk}")
        self.assertContains(response, "Avaliação térmica em andamento")
        self.assertContains(response, "ENDEREÇO PRIVADO 321")
        for texto in ("NOTA RESERVADA 9821", "RASCUNHO RESERVADO 6543", "150,25", "<progress", "Aprovar orçamento"):
            self.assertNotContains(response, texto)
        self.assertContains(response, "depois de combinado")

    def test_orcamento_acordado_soma_exata_inclusive_zero(self):
        self.os.orcamento_acordado = True
        self.os.data_acordo = timezone.localdate()
        self.os.full_clean()
        self.os.save()
        self.assertEqual(self.os.total_acordado, Decimal("195.75"))
        response = self.client.get(self.os.get_absolute_url())
        self.assertContains(response, "195,75")
        self.assertContains(response, "RASCUNHO RESERVADO 6543")
        self.assertNotContains(response, "NOTA RESERVADA 9821")
        self.os.valor_servicos = self.os.valor_pecas = self.os.valor_logistica = Decimal("0")
        self.os.full_clean()
        self.assertEqual(self.os.total_acordado, Decimal("0"))

    def test_dados_de_os_nao_aparecem_para_outro_cliente_staff_ou_publico(self):
        for user in (self.outro, self.admin):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.os.get_absolute_url()).status_code, 404)
            response = self.client.get(reverse("area_cliente:painel"))
            self.assertNotContains(response, "Revisão do notebook")
        self.client.logout()
        self.assertEqual(self.client.get(self.os.get_absolute_url()).status_code, 302)
        for name in ("home", "servicos", "contato"):
            response = self.client.get(reverse("core:" + name))
            self.assertNotContains(response, "ENDEREÇO PRIVADO 321")
            self.assertNotContains(response, "NOTA RESERVADA 9821")

    def test_os_oculta_bloqueia_mensagem_arquivo_e_detalhe(self):
        self.os.visivel_cliente = False
        self.os.save()
        self.assertEqual(self.client.get(self.os.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.post(reverse("area_cliente:enviar_mensagem", args=[self.os.pk]), {"conversa-texto": "Olá"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("area_cliente:enviar_arquivo", args=[self.os.pk]), {}).status_code, 404)

    def test_cliente_nao_pode_criar_os_nem_alterar_orcamento(self):
        response = self.client.post(self.os.get_absolute_url(), {"etapa": "entregue", "valor_servicos": "0", "orcamento_acordado": "on"})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.client.post(reverse("admin:clientes_ordemmanutencao_add"), self.payload()).status_code, 302)
        self.os.refresh_from_db()
        self.assertFalse(self.os.orcamento_acordado)
        self.assertEqual(OrdemManutencao.objects.count(), 1)

    def test_filtros_separam_manutencao_e_digital_sem_perder_progresso(self):
        url = reverse("area_cliente:painel")
        response = self.client.get(url, {"categoria": "manutencao"})
        self.assertContains(response, self.os.titulo)
        self.assertNotContains(response, self.digital.titulo)
        self.assertNotContains(response, "<progress")
        response = self.client.get(url, {"categoria": "digital"})
        self.assertContains(response, self.digital.titulo)
        self.assertNotContains(response, self.os.titulo)
        self.assertContains(response, 'value="40"')
        self.assertEqual(self.client.get(url, {"categoria": "invalido"}).context["categoria"], "todos")

    def test_arquivos_e_mensagens_reutilizam_os_sem_vazar_para_outro_cliente(self):
        with tempfile.TemporaryDirectory() as root, override_settings(PRIVATE_FILES_ROOT=root):
            response = self.client.post(reverse("area_cliente:enviar_arquivo", args=[self.os.pk]), {"anexo-titulo": "Foto do equipamento", "anexo-arquivo": SimpleUploadedFile("descricao.txt", b"Dados do equipamento")})
            self.assertEqual(response.status_code, 302)
            arquivo = ArquivoSolicitacao.objects.get()
            download = reverse("area_cliente:arquivo_download", args=[self.os.pk, arquivo.pk])
            response = self.client.get(download)
            self.assertEqual(b"".join(response.streaming_content), b"Dados do equipamento")
            self.client.post(reverse("area_cliente:enviar_mensagem", args=[self.os.pk]), {"conversa-texto": "Podemos combinar a entrega?"})
            self.assertEqual(MensagemSolicitacao.objects.get().solicitacao_id, self.os.pk)
            self.client.force_login(self.outro)
            self.assertEqual(self.client.get(download).status_code, 404)

    def test_validacoes_de_acordo_valores_datas_e_equipamentos(self):
        self.os.orcamento_acordado = True
        self.os.valor_servicos = None
        self.os.detalhes_orcamento = ""
        with self.assertRaises(ValidationError) as error:
            self.os.full_clean()
        self.assertTrue({"valor_servicos", "data_acordo", "detalhes_orcamento"}.issubset(error.exception.message_dict))
        self.os.refresh_from_db()
        self.os.valor_pecas = Decimal("-1")
        with self.assertRaises(ValidationError):
            self.os.full_clean()
        self.os.refresh_from_db()
        self.os.equipamento = "celular"
        with self.assertRaises(ValidationError):
            self.os.full_clean()
        self.os.refresh_from_db()
        self.os.entregue_em = timezone.localdate() - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.os.full_clean()
        self.os.entregue_em = None
        self.os.etapa = "entregue"
        with self.assertRaises(ValidationError):
            self.os.full_clean()

    def test_banco_rejeita_valor_negativo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrdemManutencao.objects.filter(pk=self.os.pk).update(valor_pecas=-10)

    def test_entrega_encerra_os_e_move_para_historico(self):
        self.os.etapa = "entregue"
        self.os.entregue_em = timezone.localdate()
        self.os.full_clean()
        self.os.save()
        base = Solicitacao.objects.get(pk=self.os.pk)
        self.assertTrue(base.encerrada)
        self.assertEqual(base.status_publico, "Entregue")
        response = self.client.get(reverse("area_cliente:painel"))
        self.assertIn(base, response.context["solicitacoes_encerradas"])

    def test_admin_cadastra_os_com_um_so_atendimento_e_historico(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:clientes_ordemmanutencao_add"))
        self.assertContains(response, 'name="anotacoes_internas"')
        response = self.client.post(reverse("admin:clientes_ordemmanutencao_add"), self.payload(orcamento_acordado="on", valor_servicos="100.50", data_acordo=timezone.localdate().isoformat(), detalhes_orcamento="Limpeza combinada", anotacoes_internas="Reservado"))
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        obj = OrdemManutencao.objects.get(titulo="Manutenção cadastrada")
        base = Solicitacao.objects.get(pk=obj.pk)
        self.assertEqual(base.tipo, "manutencao")
        self.assertEqual(base.status, "andamento")
        self.assertEqual(obj.atualizacoes.count(), 2)
        self.assertFalse(obj.atualizacoes.filter(mensagem__contains="Reservado").exists())
        response = self.client.get(reverse("admin:clientes_ordemmanutencao_change", args=[obj.pk]))
        self.assertContains(response, "Enviar mensagem")
        self.assertEqual(self.client.get(reverse("admin:clientes_solicitacao_change", args=[obj.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse("admin:clientes_solicitacao_change", args=[obj.pk]), {}).status_code, 403)

    def test_admin_etapa_muda_sem_percentual_e_nota_interna_permanece_privada(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:clientes_ordemmanutencao_change", args=[self.os.pk]), self.payload(etapa="testes", anotacoes_internas="Não publicar", **{"atualizacoes-TOTAL_FORMS": "1", "atualizacoes-0-titulo": "Nota interna", "atualizacoes-0-mensagem": "Não mostrar ao cliente"}))
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        update = self.os.atualizacoes.get(titulo="Etapa da manutenção atualizada")
        self.assertEqual(update.mensagem, "Em testes")
        self.assertIsNone(update.progresso_registrado)
        self.client.force_login(self.cliente)
        response = self.client.get(self.os.get_absolute_url())
        self.assertContains(response, "Em testes")
        self.assertNotContains(response, "Não publicar")
        self.assertNotContains(response, "Não mostrar ao cliente")

    def test_admin_separa_listas_e_autocomplete_ainda_encontra_os(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:clientes_solicitacao_changelist"))
        self.assertContains(response, self.digital.titulo)
        self.assertNotContains(response, self.os.titulo)
        response = self.client.get(reverse("admin:clientes_ordemmanutencao_changelist"))
        self.assertContains(response, self.os.titulo)
        response = self.client.get(reverse("admin:autocomplete"), {"app_label": "clientes", "model_name": "mensagemsolicitacao", "field_name": "solicitacao", "term": "Revisão"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], str(self.os.pk))

    def test_staff_sem_permissao_nao_acessa_notas_tecnicas(self):
        self.outro.is_staff = True
        self.outro.save()
        self.outro.user_permissions.add(Permission.objects.get(codename="view_solicitacao"))
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(reverse("admin:clientes_ordemmanutencao_change", args=[self.os.pk])).status_code, 403)
