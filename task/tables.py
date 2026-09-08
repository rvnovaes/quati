import django_tables2 as tables
from core.tables import CheckBoxMaterial
from .models import TypeTask, TaskFilterViewModel, Filter, Task


class TaskTable(tables.Table):
    def __init__(self, *args, _overriden_value="Estado", **kwargs):
        super().__init__(*args, **kwargs)
        self.base_columns['status'].verbose_name = _overriden_value
        self.length = self.rows.__len__()

    selection = CheckBoxMaterial(accessor="pk", orderable=False)
    status = tables.TemplateColumn(
        template_name="task/task_status_column.html", orderable=False)

    delegation_date = tables.DateColumn(format="d/m/Y")
    acceptance_date = tables.DateColumn(format="d/m/Y")
    final_deadline_date = tables.DateTimeColumn(short=True)
    execution_date = tables.DateColumn(format="d/m/Y")
    return_date = tables.DateColumn(format="d/m/Y")
    refused_date = tables.DateColumn(format="d/m/Y")

    class Meta:
        order_by = 'legal_name'
        model = Task
        sequence = [
            'selection', 'status', 'task_number', 'type_task',
            "person_executed_by", 'person_asked_by', "final_deadline_date",
            'delegation_date', 'acceptance_date', 'refused_date',
            'execution_date', 'return_date', 'blocked_payment_date',
            'finished_date', 'is_active'
        ]
        fields = [
            'selection', 'status', 'task_number', 'person_asked_by',
            'person_executed_by', 'type_task', 'delegation_date',
            'acceptance_date', 'final_deadline_date', 'execution_date',
            'return_date', 'refused_date', 'legacy_code',
            'blocked_payment_date', 'finished_date', 'is_active'
        ]
        empty_text = "Não existem providências cadastradas"
        row_attrs = {
            'data_href':
            lambda record: '/providencias/providencias/' + str(record.movement.id) + '/' + str(record.pk) + '/'
        }


class DashboardStatusTable(tables.Table):
    def __init__(self,
                 *args,
                 delegation_date='Delegação',
                 client="Cliente",
                 law_suit_number="Processo",
                 type_task="Serviço",
                 opposing_party="Parte adversa",
                 title="",
                 status="",
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.base_columns['client'].verbose_name = client
        self.base_columns['law_suit_number'].verbose_name = law_suit_number
        self.base_columns['type_task'].verbose_name = type_task
        self.base_columns['opposing_party'].verbose_name = opposing_party
        self.base_columns['task_number'].verbose_name = 'Nº da OS'
        self.base_columns['origin_code'].verbose_name = 'OS Original'
        self.title = title
        self.status = status

        self.length = self.rows.__len__()

    client = tables.Column(orderable=True)
    description = tables.Column(orderable=False)
    type_task = tables.Column(orderable=True)
    opposing_party = tables.Column(accessor='movement__law_suit__opposing_party')
    origin_code = tables.Column(order_by=('parent_task_number', 'legacy_code'))
    status = tables.TemplateColumn(
        template_name="task/task_status_column.html", orderable=False)
    executed_by_legal_name = tables.Column(accessor='executed_by_legal_name',
                                           verbose_name='Correspondente',
                                           orderable=True)
    # perguntar pro tiago: onde carrega asked_by_legal_name
    # asked_by_legal_name = tables.Column(accessor='asked_by_legal_name',
    #                                     verbose_name='Solicitante',
    #                                     orderable=True)

    asked_by_legal_name = tables.Column(accessor='person_asked_by',
                                        verbose_name='Solicitante',
                                        orderable=True)


    class Meta:
        model = TaskFilterViewModel
        fields = [
            'status', 'task_number', 'final_deadline_date', 'type_task',
            'law_suit_number', 'client', 'opposing_party', 'origin_code',
            'description', 'asked_by_legal_name', 'person_company_representative', 'state', 'court_district',
            'court_division', 'executed_by_legal_name'
        ]
        empty_text = "Não existem providências a serem exibidas"
        row_attrs = {
            'pk': lambda record: str(record.pk),
            'data_new_href':
            lambda record: '/dashboard/' + str(record.pk) + '/'
        }
        order_by = ('-final_deadline_date', )


class FilterTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        sequence = ('selection', 'create_user', 'name', 'description')
        model = Filter
        fields = ['selection', 'create_user', 'name', 'description']
        empty_text = "Não existem filtros cadastrados"
        row_attrs = {
            'data_href':
            lambda record: '/providencias/filtros/' + str(record.pk) + '/'
        }
        order_by = (
            'create_user',
            'name',
        )


class TypeTaskTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        sequence = ('selection', 'name', 'type_task_main', 'survey', 'survey_company_representative', 'legacy_code')
        model = TypeTask
        fields = ['name', 'type_task_main', 'survey', 'survey_company_representative', 'legacy_code']
        attrs = {"class": "table stable-striped table-bordered"}
        empty_text = "Não existem questionários cadastrados"
        row_attrs = {
            'data_href':
            lambda record: '/providencias/type_task/' + str(record.pk) + '/'
        }
        order_by = 'name'
