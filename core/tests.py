from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from .models import ConfiguracaoContato


class ContatoServicosTests(TestCase):
    def test_home_tem_tres_destinos_distintos(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'href="/area-cliente/"')
        self.assertContains(response, "Acompanhar meu atendimento")
        self.assertContains(response, "Conhecer meus projetos")
        self.assertContains(response, 'aria-label="Solicitar um serviço"')
        self.assertContains(response, 'href="/servicos/"')
        self.assertRedirects(self.client.get(reverse("area_cliente:painel")), reverse("area_cliente:entrar") + "?next=/area-cliente/", fetch_redirect_response=False)

    def test_whatsapp_so_aparece_quando_configurado_e_ativo(self):
        response = self.client.get(reverse("core:contato"))
        self.assertNotContains(response, "https://wa.me/")
        self.assertContains(response, "mailto:danilooliv.m@hotmail.com")
        obj = ConfiguracaoContato.objects.create(email="atendimento@example.com", whatsapp="5511999990000", whatsapp_ativo=False)
        self.assertNotContains(self.client.get(reverse("core:contato")), "https://wa.me/")
        obj.whatsapp_ativo = True
        obj.full_clean()
        obj.save()
        for name in ("contato", "servicos", "home"):
            self.assertContains(self.client.get(reverse("core:" + name)), "https://wa.me/5511999990000")
        self.assertContains(self.client.get(reverse("core:contato")), "mailto:atendimento@example.com")

    def test_configuracao_rejeita_url_e_numero_ausente(self):
        for numero in ("", "https://exemplo.com", "5511<script>"):
            obj = ConfiguracaoContato(whatsapp=numero, whatsapp_ativo=True)
            with self.assertRaises(ValidationError):
                obj.full_clean()

    def test_servicos_apresenta_fluxo_por_contato_sem_cadastro_publico(self):
        response = self.client.get(reverse("core:servicos"))
        self.assertContains(response, "Computadores e notebooks")
        self.assertContains(response, "Coleta e entrega mediante combinação")
        self.assertNotContains(response, 'name="cliente"')
        self.assertNotContains(response, 'name="equipamento"')

    def test_admin_configura_canal_de_contato(self):
        admin = get_user_model().objects.create_superuser(username="admin_contato", password="senha")
        self.client.force_login(admin)
        response = self.client.post(reverse("admin:core_configuracaocontato_add"), {"email": "atendimento@example.com", "whatsapp": "5511999990000", "whatsapp_ativo": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ConfiguracaoContato.objects.count(), 1)
        self.assertEqual(self.client.get(reverse("admin:core_configuracaocontato_add")).status_code, 403)
