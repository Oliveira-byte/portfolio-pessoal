from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from portfolio.models import Projeto


class FinalizacaoPublicaTests(TestCase):
    def projeto(self, **kwargs):
        dados = dict(titulo='Projeto de teste', slug='teste', resumo='Resumo do projeto', descricao='Descrição', publicado=True)
        dados.update(kwargs)
        return Projeto.objects.create(**dados)

    def test_home_mantem_apenas_apresentacao_e_acessos(self):
        response = self.client.get('/')
        self.assertContains(response, 'Acompanhar meu atendimento')
        self.assertContains(response, 'Conhecer meus projetos')
        self.assertContains(response, 'Consultar serviços')
        for section in ('home-projects', 'home-services', 'home-profile', 'p11-credentials'):
            self.assertNotContains(response, section)
        navbar = response.content.decode().split('<nav ', 1)[1].split('</nav>', 1)[0]
        self.assertNotIn('/curriculo/', navbar)
        self.assertNotIn('/competencias/', navbar)

    def test_competencias_agora_fazem_parte_do_curriculo(self):
        self.assertRedirects(self.client.get(reverse('core:competencias')),
                             reverse('core:curriculo') + '#competencias', status_code=301)
        response = self.client.get(reverse('core:curriculo'))
        self.assertContains(response, 'id="competencias"')
        for titulo in ('Desenvolvimento web', 'Requisitos e negócio', 'Métodos e colaboração',
                       'Sistemas e integrações', 'Hardware e suporte técnico', 'Dados e inteligência artificial'):
            self.assertContains(response, titulo)
        self.assertContains(response, 'danilo-oliveira-curriculo.pdf')

    @override_settings(SITE_URL='https://portfolio.example')
    def test_metadados_usam_origem_configurada_sem_query(self):
        response = self.client.get('/sobre/?campanha=teste')
        self.assertContains(response, 'rel="canonical" href="https://portfolio.example/sobre/"')
        self.assertContains(response, 'content="https://portfolio.example/static/img/brand/banner-nome.webp"')
        projeto = self.projeto(titulo='Projeto "especial" <teste>')
        response = self.client.get(projeto.get_absolute_url())
        self.assertContains(response, 'Projeto &quot;especial&quot; &lt;teste&gt; | Danilo Oliveira')
        self.assertContains(response, 'name="description" content="Resumo do projeto"')

    def test_login_nao_tem_metadados_de_pagina_publica(self):
        response = self.client.get(reverse('area_cliente:entrar'))
        self.assertContains(response, 'name="robots" content="noindex, nofollow"')
        self.assertNotContains(response, 'rel="canonical"')
        self.assertNotContains(response, 'property="og:image"')

    def test_capa_publicada_funciona_e_despublicacao_bloqueia(self):
        with TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            buffer = BytesIO()
            Image.new('RGB', (24, 24), '#163d63').save(buffer, 'PNG')
            projeto = self.projeto(capa=SimpleUploadedFile('capa.png', buffer.getvalue(), content_type='image/png'))
            url = reverse('portfolio:projeto_capa', kwargs={'slug': projeto.slug})
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), buffer.getvalue())
            response.close()
            projeto.publicado = False
            projeto.save()
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.get(projeto.capa.url).status_code, 404)

    def test_capa_ausente_retorna_404_e_pagina_usa_apresentacao_visual(self):
        projeto = self.projeto()
        self.assertEqual(self.client.get(reverse('portfolio:projeto_capa', kwargs={'slug': projeto.slug})).status_code, 404)
        response = self.client.get(projeto.get_absolute_url())
        self.assertContains(response, 'monograma.webp')
        self.assertContains(response, 'ainda não tem um endereço público')
