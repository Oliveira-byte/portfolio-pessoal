from html.parser import HTMLParser
from django.test import TestCase
from django.urls import reverse
from .models import ConfiguracaoContato
from .servicos_catalogo import SERVICOS


class FormulariosHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.labels = []
        self.forms = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'label':
            self.labels.append(attrs.get('for'))
        if tag == 'form' and 'data-form-servico' in attrs:
            self.forms.append(attrs)
        if tag == 'a':
            self.links.append(attrs)


class MensagemServicosTests(TestCase):
    def test_nove_categorias_com_formularios_e_labels_unicos(self):
        response = self.client.get(reverse('core:servicos'))
        html = FormulariosHTML()
        html.feed(response.content.decode())
        self.assertEqual(len(html.forms), 9)
        self.assertEqual(len(html.ids), len(set(html.ids)))
        self.assertTrue(all(label in html.ids for label in html.labels))
        for servico in SERVICOS:
            self.assertContains(response, f'data-servico="{servico["slug"]}"', count=1)
            self.assertContains(response, f'data-form-servico="{servico["slug"]}"', count=1)
        self.assertNotContains(response, 'Seu atendimento está aqui.')
        self.assertContains(response, 'href="/contato/">Conversar sobre um projeto')
        self.assertContains(response, '<noscript>')

    def test_canais_configurados_e_whatsapp_somente_ativo(self):
        config = ConfiguracaoContato.objects.create(email='servicos@example.com', whatsapp='5543999990000', whatsapp_ativo=False)
        response = self.client.get(reverse('core:servicos'))
        self.assertContains(response, 'data-email="servicos@example.com"', count=9)
        self.assertNotContains(response, 'data-link-whatsapp')
        config.whatsapp_ativo = True
        config.save()
        response = self.client.get(reverse('core:servicos'))
        self.assertContains(response, 'data-link-whatsapp', count=9)
        self.assertContains(response, 'data-whatsapp="https://wa.me/5543999990000"', count=9)

    def test_formularios_nao_tem_destino_de_envio_automatico(self):
        html = FormulariosHTML()
        html.feed(self.client.get(reverse('core:servicos')).content.decode())
        for form in html.forms:
            self.assertNotIn('action', form)
            self.assertNotIn('method', form)
        for link in html.links:
            if 'data-link-email' in link or 'data-link-whatsapp' in link:
                self.assertNotIn('href', link)
