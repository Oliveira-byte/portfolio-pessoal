from django.core.management.base import BaseCommand
from django.db import transaction

from portfolio.models import Projeto, Tecnologia


class Command(BaseCommand):
    help = "Cadastra os dois projetos iniciais; preserva projetos já existentes pelo slug."

    @transaction.atomic
    def handle(self, *args, **options):
        dados = [
            {
                "slug": "atlas-semi-joias",
                "titulo": "Atlas Semi-Joias",
                "categoria": "Comércio digital",
                "resumo": "Plataforma de e-commerce para joias personalizadas, com fluxo de personalização e área de usuário.",
                "descricao": "Projeto pessoal de uma loja virtual para semi-joias personalizadas. A proposta é reunir apresentação dos produtos, informações de gravação e dados do cliente em uma experiência organizada.",
                "desafio": "Organizar a escolha de uma joia e as informações de personalização em uma experiência acessível.",
                "solucao": "Estruturação das páginas, identidade visual e desenvolvimento do fluxo de personalização e cadastro de clientes com Django.",
                "aprendizados": "O projeto segue em desenvolvimento, com refinamentos na navegação, nos formulários e na experiência de compra.",
                "capa_estilo": Projeto.CapaEstilo.ATLAS,
                "destaque": True, "ordem": 1,
                "tecnologias": ["Python", "Django", "JavaScript", "Bootstrap"],
            },
            {
                "slug": "portfolio-pessoal",
                "titulo": "Portfólio Pessoal",
                "categoria": "Presença profissional",
                "resumo": "Site multipágina para apresentar minha trajetória, competências e projetos de tecnologia.",
                "descricao": "Portfólio profissional construído com Django. Cada área possui sua própria página, mantendo uma identidade visual compartilhada e navegação na mesma aba.",
                "desafio": "Apresentar informações profissionais com clareza e permitir que novos projetos sejam incluídos pelo painel administrativo.",
                "solucao": "Organização dos templates, criação da identidade azul e cinza e implementação de projetos cadastrados no banco, com listagem e páginas individuais.",
                "aprendizados": "Evolução da estrutura de modelos, rotas e templates do Django. A área do cliente continua no planejamento para uma etapa futura.",
                "capa_estilo": Projeto.CapaEstilo.PADRAO,
                "destaque": False, "ordem": 2,
                "tecnologias": ["Django", "HTML", "CSS", "Bootstrap"],
            },
        ]
        for item in dados:
            nomes = item.pop("tecnologias")
            slug = item.pop("slug")
            projeto, criado = Projeto.objects.get_or_create(
                slug=slug, defaults={**item, "publicado": True},
            )
            if criado:
                projeto.tecnologias.set([
                    Tecnologia.objects.get_or_create(nome=nome)[0] for nome in nomes
                ])
                self.stdout.write(self.style.SUCCESS(f"Criado: {projeto.titulo}"))
            else:
                self.stdout.write(f"Preservado: {projeto.titulo}")
