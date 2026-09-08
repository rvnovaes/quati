import json
from django import forms
from django.forms import ModelForm
from django.utils import timezone
from core.widgets import MultipleFileField

from core.models import Person, ImportXlsFile
from core.utils import filter_valid_choice_form, get_office_field, get_office_session
from core.widgets import MDDateTimepicker, MDSelect
from core.forms import BaseForm, XlsxFileField
from lawsuit.models import CourtDistrict, CourtDistrictComplement, City, Movement, LawSuit, Folder
from task.models import Task, TypeTask, Filter, TaskStatus, TypeTaskMain, TaskSurveyAnswer, TaskBase
from task.resources import COLUMN_NAME_DICT
from task.utils import validate_final_deadline_date
from task.widgets import code_mirror_schema
from .schemas import *
from .fields import JSONFieldMixin
from survey.models import Survey
from manager.utils import get_template_value_value
from manager.enums import TemplateKeys


class TaskForm(BaseForm):
    task_number = forms.CharField(
        disabled=True,
        required=False,
        widget=forms.TextInput(
            attrs={'placeholder': 'Gerado automaticamente'}))

    class Meta:
        model = Task
        fields = [
            'office', 'task_number', 'person_asked_by', 'person_company_representative', 'type_task',
            'final_deadline_date', 'performance_place', 'description', 'is_active', 'legacy_code'
        ]

    person_asked_by = forms.ModelChoiceField(
        empty_label='Selecione...',
        queryset=filter_valid_choice_form(Person.objects.active().requesters().
                                          active_offices().order_by('name')))

    person_company_representative = forms.ModelChoiceField(
        empty_label='Selecione...',
        required=False,
        queryset=filter_valid_choice_form(
            Person.objects.active().filter(
                legal_type='F').order_by('name')))

    type_task = forms.ModelChoiceField(
        queryset=filter_valid_choice_form(
            TypeTask.objects.filter(is_active=True)).order_by('name'),
        empty_label='Selecione...',
        label='Tipo de Serviço')

    final_deadline_date = forms.DateTimeField(
        required=True,
        label="Prazo Fatal",
        widget=MDDateTimepicker(
            attrs={'class': 'form-control'}, format='DD/MM/YYYY HH:mm'))

    description = forms.CharField(
        required=False,
        initial='',
        label='Descrição',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': '5',
            'id': 'details_id'
        }))

    performance_place = forms.CharField(required=True)
    documents = MultipleFileField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)
        office_session = get_office_session(self.request)
        if office_session:
            self.fields['person_asked_by'].queryset = filter_valid_choice_form(
                Person.objects.active().requesters(
                    office_id=office_session.pk).active_offices().order_by(
                        'name'))
            self.fields['type_task'].queryset = filter_valid_choice_form(
                TypeTask.objects.filter(
                    is_active=True, office=office_session)).order_by('name')
        else:
            self.fields['type_task'].queryset = TypeTask.objects.none()
        if self.request.user:
            if Person.objects.requesters().filter(auth_user=self.request.user):
                self.fields[
                    'person_asked_by'].initial = self.request.user.person

    def clean(self):
        super().clean()
        office = self.cleaned_data.get('office')
        final_deadline_date = self.cleaned_data.get('final_deadline_date')
        if office and final_deadline_date and not validate_final_deadline_date(final_deadline_date, office):
            min_hour_os = get_template_value_value(office, TemplateKeys.MIN_HOUR_OS.name)
            msg = 'O prazo de cumprimento da OS foi configurado para não poder ser inferior à {} hora(s).'.format(min_hour_os)
            self.add_error('final_deadline_date', forms.ValidationError(msg))


class TaskCreateForm(TaskForm):
    documents = MultipleFileField(required=False)

    class Meta(TaskForm.Meta):
        fields = TaskForm.Meta.fields + ['documents']


class TaskBulkCreateForm(TaskCreateForm):
    task_law_suit_number = forms.ModelChoiceField(label='Número do processo',
                                                  required=False,
                                                  widget=MDSelect(url='/processos/lawsuit_autocomplete',
                                                                  forward=['person_customer']),
                                                  queryset=LawSuit.objects.all())
    court_district = forms.ModelChoiceField(label='Comarca',
                                            required=False,
                                            widget=MDSelect(url='/processos/courtdistrict_select2', ),
                                            queryset=CourtDistrict.objects.all())
    city = forms.ModelChoiceField(label='Cidade',
                                  required=False,
                                  widget=MDSelect(url='/city/autocomplete_select2/', ),
                                  queryset=City.objects.all())
    court_district_complement = forms.ModelChoiceField(label='Complemento de Comarca',
                                                       required=False,
                                                       widget=MDSelect(url='/processos/complemento_select2',
                                                                       forward=['court_district']),
                                                       queryset=CourtDistrictComplement.objects.all())
    person_customer = forms.ModelChoiceField(label='Cliente/Parte',
                                             required=True,
                                             widget=MDSelect(url='/get_client_2', ),
                                             queryset=Person.objects.all())
    person_customer_swal = forms.ModelChoiceField(label='Cliente/Parte',
                                                  required=True,
                                                  widget=MDSelect(url='/get_client_2', ),
                                                  queryset=Person.objects.all())

    folder_number = forms.ModelChoiceField(label='Nº da Pasta',
                                           required=False,
                                           widget=MDSelect(url='/processos/folder_autocomplete_2',
                                                           forward=['task_law_suit_number', 'person_customer']),
                                           queryset=Folder.objects.all())
    movement = forms.ModelChoiceField(label='Movimentação',
                                      required=False,
                                      widget=MDSelect(url='/processos/movement_autocomplete',
                                                      forward=['task_law_suit_number']),
                                      queryset=Movement.objects.all())
    person_company_representative = forms.ModelChoiceField(label='Preposto',
                                                           required=False,
                                                           widget=MDSelect(url='/get_person_company_representative_2', ),
                                                           queryset=Person.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        office_session = get_office_session(self.request)
        self.fields['performance_place'].widget = forms.HiddenInput()
        self.fields['task_number'].widget = forms.HiddenInput()
        self.fields['office'].widget = forms.HiddenInput()
        self.fields['office'].initial = office_session
        self.fields['person_asked_by'].empty_label = 'Procurar...'
        choices = [choice for choice in self.fields['person_asked_by'].choices]
        if (self.request.user.person.id, self.request.user.person.legal_name) not in choices:
            choices.append((self.request.user.person.id, self.request.user.person.legal_name))
        self.fields['person_asked_by'].choices = choices


class TaskDetailForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ModelForm, self).__init__(*args, **kwargs)
        self.fields['execution_date'].widget.max_date = timezone.now()

    class Meta:
        model = Task
        fields = ['execution_date', 'survey_result']

    survey_result = forms.CharField(
        required=False, initial=None, widget=forms.HiddenInput())

    execution_date = forms.DateTimeField(
        required=False,
        initial=timezone.now(),
        label='Data de Cumprimento',
        widget=MDDateTimepicker(
            attrs={
                'class': 'form-control',
            }, format='DD/MM/YYYY HH:mm'))
    notes = forms.CharField(
        required=False,
        initial='',
        label='Insira um comentário',
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'form-control',
            'cols': '5',
            'id': 'notes_id'
        }))

    amount = forms.CharField(
        required=False,
        label='Valor:',
        widget=forms.TextInput(attrs={'mask': 'money'}))

    servicepricetable_id = forms.CharField(
        required=False, widget=forms.HiddenInput())

    feedback_rating = forms.IntegerField(label="Nota", required=False)
    feedback_comment = forms.CharField(
        label="Comentário sobre o atendimento do correspondente",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}))

    def clean_amount(self):
        amount = (self.cleaned_data['amount']
                  if self.cleaned_data['amount'] else str(0))
        amount = amount.replace('.', '')
        amount = amount.replace(',', '.')
        return float(amount)

    def clean(self):
        form_data = self.cleaned_data
        return form_data


class FilterForm(BaseForm):
    name = forms.CharField(
        label=u"Nome",
        required=True,
        widget=forms.Textarea(attrs={'rows': '1'}))
    description = forms.CharField(
        label=u"Descrição",
        required=False,
        widget=forms.Textarea(attrs={'rows': '3'}))

    class Meta:
        model = Filter
        fields = ['name', 'description']


class TaskToAssignForm(BaseForm):
    class Meta:
        model = Task
        fields = ['person_executed_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_executed_by'].required = True


class TaskChangeAskedBy(BaseForm):
    class Meta:
        model = Task
        fields = ['person_asked_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_asked_by'].required = True

class TaskChangeRepresentativeBy(BaseForm):
    class Meta:
        model = Task
        fields = ['person_company_representative']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_company_representative'].required = True
#

class TypeTaskMainForm(forms.ModelForm):
    characteristics = JSONFieldMixin(
        label="Caractersíticas",
        widget=code_mirror_schema,
        initial=CHARACTERISTICS)

    class Meta:
        model = TypeTaskMain
        fields = '__all__'


class TypeTaskForm(BaseForm):
    class Meta:
        model = TypeTask
        fields = ['office', 'type_task_main', 'survey', 'survey_company_representative', 'name', 'is_active', 'legacy_code']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        office = get_office_session(self.request)
        self.fields['office'] = get_office_field(self.request)
        self.fields['survey'].queryset = Survey.objects.filter(office=office)
        self.fields['survey_company_representative'].queryset = Survey.objects.filter(office=office)
        self.order_fields(
            ['office', 'type_task_main', 'survey', 'survey_company_representative', 'name', 'is_active', 'legacy_code'])


class ImportTaskListForm(forms.ModelForm):
    file_xls = XlsxFileField(
        label='Arquivo', required=True, headers_to_check=[])

    class Meta:
        model = ImportXlsFile
        fields = ('file_xls', )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file_xls'].headers_to_check.extend([
            v['column_name'] for k, v in COLUMN_NAME_DICT.items()
            if v['required']
        ])


class TaskSurveyAnswerForm(forms.ModelForm):
    class Meta:
        model = TaskSurveyAnswer
        fields = ('create_user', 'survey_result')