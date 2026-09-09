import django_tables2 as tables
from .models import InconsistencyETL


class DashboardErrorStatusTable(tables.Table):
    def __init__(self, *args, title="", status="", **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.status = status

        self.length = self.rows.__len__()

    task_number = tables.Column(
        accessor='task__task_number', verbose_name="Número da Providência")
    final_deadline_date = tables.Column(
        accessor='task__final_deadline_date', verbose_name="Prazo")
    type_service = tables.Column(
        accessor='task__type_task__name', verbose_name="Serviço")
    lawsuit_number = tables.Column(
        accessor='task__movement__law_suit__law_suit_number',
        verbose_name="Processo")
    client = tables.Column(
        accessor='task__movement__law_suit__folder__person_customer',
        verbose_name="Cliente")
    opposing_party = tables.Column(
        accessor='task__movement__law_suit__opposing_party',
        verbose_name="Parte adversa")
    delegation_date = tables.Column(
        accessor='task__delegation_date', verbose_name="Delegação")
    legacy_code = tables.Column(
        accessor='task__legacy_code', verbose_name="Código Legado")
    inconsistency_desc = tables.Column(
        order_by=('inconsistency'), verbose_name="Inconsistência")
    solution = tables.Column(verbose_name="Solução")

    class Meta:
        model = InconsistencyETL
        fields = [
            'task_number', 'final_deadline_date', 'type_service',
            'lawsuit_number', 'client', 'opposing_party', 'delegation_date',
            'legacy_code', 'inconsistency_desc', 'solution'
        ]
        empty_text = "Não existem providências a serem exibidas"
        row_attrs = {
            'data_new_href':
            lambda record: '/dashboard/' + str(record.task.id) + '/'
        }
        order_by = ('task_number', )
