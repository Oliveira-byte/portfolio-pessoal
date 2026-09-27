from django.core.management.base import BaseCommand
from comunicacao.models import EntregaEmail
from comunicacao.services import processar_entrega


class Command(BaseCommand):
    help = "Processa e-mails pendentes. Use --repetir-falhas para tentar novamente os que falharam."

    def add_arguments(self, parser):
        parser.add_argument("--repetir-falhas", action="store_true")
        parser.add_argument("--limite", type=int, default=100)

    def handle(self, *args, **options):
        estados = ["pendente", "falha"] if options["repetir_falhas"] else ["pendente"]
        ids = list(EntregaEmail.objects.filter(estado__in=estados).order_by("pk").values_list("pk", flat=True)[:max(0, options["limite"])])
        concluidos = sum(processar_entrega(pk) for pk in ids)
        self.stdout.write(f"Processados: {len(ids)}. Aceitos pelo backend: {concluidos}. Consulte o estado no painel de e-mails.")
