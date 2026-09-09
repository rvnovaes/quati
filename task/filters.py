from datetime import datetime, time
from django.forms import Select, Textarea, RadioSelect
from django_filters import FilterSet, ModelChoiceFilter, NumberFilter, CharFilter, ChoiceFilter, MultipleChoiceFilter, \
    BooleanFilter, ModelMultipleChoiceFilter, RangeFilter, Filter
from dal import autocomplete
from django.db.models import Q
from core.models import Person, State, Office, Team
from core.widgets import MDDateTimeRangeFilter, TypeaHeadForeignKeyWidget, MDSelect
from financial.models import CostCenter
from lawsuit.models import CourtDistrict, Organ, CourtDistrictComplement
from task.models import TypeTask, Task, Filter, TaskStatus
from task.widgets import ApiDatetimeRangeField
from .models import TaskFilterViewModel, TypeTaskMain
from core.utils import get_office_session
from task.utils import get_status_to_filter

from django_filters import rest_framework as filters

OFFICE = 'E'
CLIENT = 'C'
GROUP_BY_TASK_TO_PAY_TYPE = (
    (OFFICE, 'Por Escritório Correspondente'),
    (CLIENT, 'Por Cliente'),
)

GROUP_BY_TASK_TO_RECEIVE_TYPE = (
    (OFFICE, 'Por Escritório Contratante'),
    (CLIENT, 'Por Cliente'),
)


class DatetimeFromToRangeFilter(RangeFilter):
    field_class = ApiDatetimeRangeField


class MultiValueCharFilter(filters.BaseCSVFilter, filters.CharFilter):
    def filter(self, qs, value):
        # value is either a list or an 'empty' value
        values = value or []
        qs = super(MultiValueCharFilter, self).filter(qs, values)

        return qs


class TaskApiFilter(FilterSet):
    is_hearing = filters.BooleanFilter(field_name='type_task__type_task_main__is_hearing')
    office_id = MultiValueCharFilter(field_name='office_id', lookup_expr='in')
    person_executed_by_id = MultiValueCharFilter(field_name='person_executed_by_id', lookup_expr='in')
    final_deadline_date = DatetimeFromToRangeFilter()
    finished_date = DatetimeFromToRangeFilter()
    task_status = MultiValueCharFilter(field_name='task_status', lookup_expr='in')
    parent_id = filters.NumberFilter(field_name='parent_id')

    class Meta:
        model = Task
        fields = ['legacy_code', 'task_number', 'is_hearing', 'office_id', 'final_deadline_date',
                  'task_status', 'person_executed_by_id', 'parent_id', 'finished_date']


class TaskDashboardApiFilter(TaskApiFilter):
    finished_date = DatetimeFromToRangeFilter()

    class Meta:
        model = TaskFilterViewModel
        fields = ['legacy_code', 'task_number', 'is_hearing', 'office_id', 'final_deadline_date',
                  'task_status', 'person_executed_by_id', 'parent_id', 'finished_date']


class TaskFilter(FilterSet):
    state = ModelMultipleChoiceFilter(
        queryset=State.objects.filter(is_active=True),
        label="UF",
        widget=autocomplete.ModelSelect2Multiple(url='state-autocomplete'))
    court_district = ModelMultipleChoiceFilter(
        queryset=CourtDistrict.objects.all(),
        label='Comarca',
        widget=autocomplete.ModelSelect2Multiple(url='courtdistrict_filter_select2', forward=['state']))
    court_district_complement = ModelChoiceFilter(label='Complemento de Comarca',
                                                  required=False,
                                                  widget=MDSelect(url='/processos/complement_filter_select2',
                                                                  forward=['court_district']),
                                                  queryset=CourtDistrictComplement.objects.all())
    task_status = MultipleChoiceFilter(
        label="Status",
        required=False,
        choices=[(task_status.name, task_status.value)
                 for task_status in TaskStatus])
    type_task = ModelMultipleChoiceFilter(
        queryset=TypeTask.objects.all(),
        label='Tipo de Serviço',
        widget=autocomplete.ModelSelect2Multiple(url='type-task-filter-autocomplete'))
    type_task_main = ModelMultipleChoiceFilter(
        queryset=TypeTaskMain.objects.all(),
        label='Tipo de Serviço Principal',
        widget=autocomplete.ModelSelect2Multiple(url='type-task-main-autocomplete'))    
    cost_center = ModelChoiceFilter(label="Setor",
                                    required=False,
                                    widget=MDSelect(url='/financeiro/centros-de-custos/filter_autocomplete',),
                                    queryset=CostCenter.objects.all(),)
    court = ModelChoiceFilter(label="Órgão",
                              required=False,
                              widget=MDSelect(url='/processos/organ_filter_select2_autocomplete', ),
                              queryset=Organ.objects.all(),)
    team = ModelChoiceFilter(label="Equipe",
                             required=False,
                             widget=MDSelect(url='/teams/filter_autocomplete_select2/', ),
                             queryset=Team.objects.all(),)
    folder_number = NumberFilter(label=u"Nº da pasta")
    folder_legacy_code = CharFilter(label=u"Nº da pasta de origem")
    law_suit_number = CharFilter(label=u"Nº do processo")
    task_number = NumberFilter(label=u"Nº da OS")
    task_legacy_code = CharFilter(label=u"Nº da OS de origem")
    task_origin_code = NumberFilter(label=u"Nº da OS de origem")
    client = ModelMultipleChoiceFilter(
        queryset=Person.objects.filter(is_customer=True),
        label='Cliente',
        widget=autocomplete.ModelSelect2Multiple(url='client_filter_select2'))
    office_executed_by = ModelChoiceFilter(
        label='Escritório contratado',
        required=False,
        widget=MDSelect(url='/office_correspondent_form', ),
        queryset=Office.objects.all())
    person_executed_by = ModelChoiceFilter(
        label="Correspondente",
        required=False,
        widget=MDSelect(url='/correspondent_form', ),)
    person_asked_by = ModelChoiceFilter(
        label="Solicitante",
        required=False,
        widget=MDSelect(url='/requester_form', ),
        queryset=Person.objects.requesters().none())
    origin_office_asked_by = ModelChoiceFilter(
        label="Solicitante de origem",
        required=False,
        widget=MDSelect(url='/origin_requester_form'),
        queryset=Office.objects.all())
    person_distributed_by = ModelChoiceFilter(
        label="Contratante",
        required=False,
        widget=MDSelect(url='/service_form', ), )
    final_deadline_date_in = MDDateTimeRangeFilter(
        name='final_deadline_date_in', label='Prazo entre:')
    requested_in = MDDateTimeRangeFilter(
        name='requested_in', label=u"Solicitadas entre:")
    accepted_service_in = MDDateTimeRangeFilter(
        name='accepted_service_in', label="Aceitas pelo Service entre:")
    refused_service_in = MDDateTimeRangeFilter(
        name='refused_service_in', label="Recusadas pelo Service entre:")
    open_in = MDDateTimeRangeFilter(field_name='open_in', label="Abertas entre:")
    accepted_in = MDDateTimeRangeFilter(
        name='accepted_in', label="Aceitas entre:")
    refused_in = MDDateTimeRangeFilter(
        name='refused_in', label="Recusadas entre:")
    return_in = MDDateTimeRangeFilter(
        name='return_in', label="Retornadas entre:")
    done_in = MDDateTimeRangeFilter(field_name='done_in', label="Cumpridas entre:")
    blocked_payment_in = MDDateTimeRangeFilter(
        name='blocked_payment_in', label="Glosadas entre:")
    finished_in = MDDateTimeRangeFilter(
        name='finished_in', label="Finalizadas entre:")

    custom_filter = ModelChoiceFilter(
        queryset=Filter.objects.all(),
        label="Escolher filtro salvo",
        required=False,
        widget=Select(attrs={'onchange': 'this.form.submit()'}))
    custom_filter_name = CharFilter(label=u"Nome do Filtro", required=False)

    custom_filter_description = CharFilter(
        label=u"Descrição",
        required=False,
        widget=Textarea(attrs={
            'class': 'form-control',
            'rows': '3'
        }))

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None, **kwargs):
        super(TaskFilter, self).__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.filters['custom_filter'].queryset = Filter.objects.filter(
            create_user=self.request.user).order_by('name')
        filters_list = ['type_task', 'cost_center', 'court', 'team']
        office_session = get_office_session(self.request)
        for filter_field in filters_list:
            self.filters[filter_field].queryset = self.filters[
                filter_field].queryset.filter(office=office_session)
        custom_settings = getattr(office_session, 'customsettings', None)
        if custom_settings and custom_settings.task_status_show:
            task_status_choices = list(
                custom_settings.task_status_show.values_list(
                    'status_to_show', flat=True).order_by('status_to_show'))
            self.filters['task_status'].extra['choices'] = self.set_task_status_choices(task_status_choices)
        self.filters['person_asked_by'].queryset = Person.objects.requesters().filter(offices=office_session)
        self.filters['person_executed_by'].queryset = Person.objects.correspondents(office_id=office_session.id)
        self.filters['person_distributed_by'].queryset = Person.objects.services().filter(offices=office_session)
        self.filters['office_executed_by'].queryset = \
            self.filters['origin_office_asked_by'].queryset = office_session.related_offices

    class Meta:
        model = TaskFilterViewModel
        fields = []
        order_by = ['final_deadline_date']

    @staticmethod
    def set_task_status_choices(status_choices):
        status_choices.sort()
        return list(map(lambda x: (TaskStatus(x).name, x), status_choices))


class BatchChangTaskFilter(TaskFilter):
    def __init__(self, data=None, queryset=None, prefix=None, strict=None, request=None):
        super().__init__(data, queryset, prefix, strict, request)
        status_to_filter = get_status_to_filter(request.option)
        self.filters['task_status'].extra['choices'] = self.set_task_status_choices(status_to_filter)


class TaskReportFilterBase(FilterSet):
    finished_in = MDDateTimeRangeFilter(field_name='finished_in')

    client = CharFilter(label="Cliente", required=False)
    office = CharFilter(label="Escritório Correspondente", required=False)

    class Meta:
        model = Task
        fields = []


class TaskToPayFilter(TaskReportFilterBase):
    status = ChoiceFilter(
        empty_label='Todas',
        choices=(
            (0, 'Somente faturadas'),
            (1, 'Somente não faturadas'),
        ))
    group_by_tasks = ChoiceFilter(
        empty_label=None,
        choices=GROUP_BY_TASK_TO_PAY_TYPE
    )
    refunds_correspondent_service = ChoiceFilter(
        label='Cliente reembolsa valor gasto com serviço de correspondência',
        empty_label='Todos',
        choices=(
            (True, 'Somente clientes que reembolsam'),
            (False, 'Somente clientes que não reembolsam'),
            )
        )


class TaskToReceiveFilter(TaskReportFilterBase):
    status = ChoiceFilter(
        empty_label='Todas',
        choices=(
            ('true', 'Somente recebidas'),
            ('false', 'Somente não recebidas'),
        ))
    group_by_tasks = ChoiceFilter(
        empty_label=None, choices=GROUP_BY_TASK_TO_RECEIVE_TYPE)
    parent_finished_in = MDDateTimeRangeFilter(field_name='parent_finished_in')


class TypeTaskMainFilter(filters.FilterSet):
    is_hearing = filters.BooleanFilter(field_name='is_hearing')
    name = filters.CharFilter(field_name='name', lookup_expr='unaccent__icontains')

    class Meta:
        model = TypeTaskMain
        fields = ['is_hearing', 'name']


class TaskCheckinReportFilter(FilterSet):
    finished_date = MDDateTimeRangeFilter(field_name='finished_date', label='TESTE')
    execution_date = MDDateTimeRangeFilter(field_name='execution_date')
    task_executed_by = CharFilter(field_name='executed_by_checkin__create_user__person__legal_name',
                                  lookup_expr='unaccent__icontains', label='Correspondente/Escritório contratado')
    task_company_representative = CharFilter(field_name='company_representative_checkin__create_user__person__legal_name',
                                             lookup_expr='unaccent__icontains', label='Preposto')
    has_checkin = ChoiceFilter(
        empty_label='Todas',
        label='Por check-in',
        method='has_checkin_filter',
        choices=(
            (0, 'Somente realizado'),
            (1, 'Somente não realizado'),
        ))

    class Meta:
        model = Task
        fields = ['finished_date', 'execution_date', 'task_executed_by', 'task_company_representative', 'has_checkin']

    def has_checkin_filter(self, queryset, name, value):
        if value == '0':
            return queryset.filter(Q(
                Q(executed_by_checkin__isnull=int(value)) |
                Q(company_representative_checkin__isnull=int(value))
            ))
        elif value == '1':
            return queryset.filter(Q(
                Q(executed_by_checkin__isnull=int(value)),
                Q(company_representative_checkin__isnull=int(value))
            ))
        return queryset
