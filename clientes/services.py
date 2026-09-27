"""Registro de andamento compartilhado entre as duas interfaces administrativas."""
from django.db import transaction
from .models import AtualizacaoSolicitacao, OrdemManutencao


@transaction.atomic
def salvar_atendimento(obj, autor, anterior=None):
    obj.save()
    liberado = bool(anterior and not anterior.visivel_cliente and obj.visivel_cliente)
    if isinstance(obj, OrdemManutencao):
        if not anterior or anterior.etapa != obj.etapa or liberado:
            AtualizacaoSolicitacao.objects.create(
                solicitacao=obj, titulo="Etapa da manutenção atualizada" if anterior else "Ordem de serviço cadastrada",
                mensagem=obj.get_etapa_display(), autor=autor,
            )
        campos = ("detalhes_orcamento", "valor_servicos", "valor_pecas", "valor_logistica", "data_acordo", "pagamento_combinado")
        if obj.orcamento_acordado and (not anterior or not anterior.orcamento_acordado or any(getattr(anterior, campo) != getattr(obj, campo) for campo in campos)):
            AtualizacaoSolicitacao.objects.create(
                solicitacao=obj, titulo="Orçamento acordado registrado",
                mensagem=f"{obj.detalhes_orcamento}\nTotal acordado: R$ " + format(obj.total_acordado, ".2f").replace(".", ","), autor=autor,
            )
    elif not anterior or anterior.status != obj.status or anterior.progresso != obj.progresso or liberado:
        AtualizacaoSolicitacao.objects.create(
            solicitacao=obj, titulo="Andamento atualizado" if anterior else "Solicitação cadastrada",
            mensagem=f"{obj.get_status_display()} · Progresso informado: {obj.progresso}%.",
            status_registrado=obj.status, progresso_registrado=obj.progresso, autor=autor,
        )
    return obj
