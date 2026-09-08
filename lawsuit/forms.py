from django import forms
from core.fields import CustomBooleanField
from core.models import Person, State, City
from financial.models import CostCenter
from .models import (TypeMovement, Instance, Movement, Folder, CourtDistrict, LawSuit, CourtDivision, Organ,
                     CourtDistrictComplement)
from core.utils import filter_valid_choice_form, get_office_field, get_office_session
from localflavor.br.forms import BRCNPJField
from core.widgets import TypeaHeadForeignKeyWidget, MDSelect
from core.forms import BaseForm


class TypeMovementForm(BaseForm):
    class Meta:
        model = TypeMovement
        fields = ['office', 'name', 'is_default', 'is_active', 'legacy_code']

    name = forms.CharField(
        max_length=255,
        required=True,
        error_messages={'required': 'O campo de descrição é obrigatório'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)


class InstanceForm(BaseForm):
    class Meta:
        model = Instance
        fields = ['office', 'name', 'is_active', 'legacy_code']

    name = forms.CharField(
        label=u"Nome da Instância",
        max_length=255,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)


class MovementForm(BaseForm):
    class Meta:
        model = Movement
        fields = ['office', 'type_movement', 'is_active', 'legacy_code']

    type_movement = forms.ModelChoiceField(
        queryset=filter_valid_choice_form(
            TypeMovement.objects.filter(is_active=True)).order_by('name'),
        empty_label=u"Selecione...",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)


class FolderForm(BaseForm):
    class Meta:
        model = Folder
        fields = [
            'office', 'folder_number', 'person_customer', 'cost_center', 'is_default', 'is_active', 'legacy_code'
        ]

    folder_number = forms.CharField(
        widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    person_customer = forms.CharField(
        label="Cliente",
        required=True,
        widget=TypeaHeadForeignKeyWidget(
            model=Person,
            field_related='legal_name',
            name='person_customer',
            url='/client_form'))
    cost_center = forms.CharField(
        required=False,
        label="Centro de Custo",
        widget=TypeaHeadForeignKeyWidget(
            model=CostCenter,
            field_related='name',
            name='cost_center',
            url='/financeiro/centros-de-custos/autocomplete'))

    def __init__(self, *args, **kwargs):
        super(FolderForm, self).__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)
        self.order_fields(
            ['office', 'folder_number', 'person_customer', 'cost_center', 'is_default', 'is_active', 'legacy_code'])

        if not self.instance.pk:
            # Since the pk is set this is not a new instance
            self.fields.pop('folder_number')


class LawSuitForm(BaseForm):
    def __init__(self, *args, **kwargs):
        super(LawSuitForm, self).__init__(*args, **kwargs)
        office_session = get_office_session(self.request)
        self.fields['office'] = get_office_field(self.request)
        self.fields['instance'].queryset = self.fields['instance'].queryset.filter(
            office=office_session)
        self.fields['court_division'].queryset = self.fields['court_division'].queryset.filter(
            office=office_session)

    class Meta:
        model = LawSuit
        fields = [
            'office', 'type_lawsuit', 'law_suit_number', 'court_district', 'city', 'court_district_complement',
            'organ', 'instance', 'court_division', 'person_lawyer', 'opposing_party', 'is_current_instance',
            'is_active', 'legacy_code', 'notes'
        ]

    person_lawyer = forms.ModelChoiceField(
        empty_label=u"Selecione",
        queryset=filter_valid_choice_form(
            Person.objects.filter(
                is_active=True,
                is_lawyer=True)).only('legal_name').order_by('name'),
        required=False)
    court_district = forms.ModelChoiceField(label='Comarca',
                                            required=False,
                                            widget=MDSelect(url='/processos/courtdistrict_select2',
                                                            forward=['city']),
                                            queryset=CourtDistrict.objects.all())
    city = forms.ModelChoiceField(label='Cidade',
                                  required=False,
                                  widget=MDSelect(url='/city/autocomplete_select2/',
                                                  forward=['court_district']),
                                  queryset=City.objects.all())
    court_district_complement = forms.ModelChoiceField(label='Complemento de Comarca',
                                                       required=False,
                                                       widget=MDSelect(url='/processos/complemento_select2',
                                                                       forward=['court_district']),
                                                       queryset=CourtDistrictComplement.objects.all())
    organ = forms.ModelChoiceField(label="Órgão",
                                   required=False,
                                   widget=MDSelect(url='/processos/organ_autocomplete', ),
                                   queryset=Organ.objects.all(), )
    instance = forms.ModelChoiceField(
        queryset=filter_valid_choice_form(
            Instance.objects.filter(is_active=True)).order_by('name'),
        empty_label=u"Selecione",
        required=False)
    court_division = forms.ModelChoiceField(
        queryset=filter_valid_choice_form(
            CourtDivision.objects.filter(is_active=True)).order_by('name'),
        empty_label=u"Selecione",
        required=False)
    opposing_party = forms.CharField(required=False)
    law_suit_number = forms.CharField(max_length=255, required=True)
    is_current_instance = CustomBooleanField(initial=False, required=False)
    notes = forms.CharField(required=False,
                            label='Observações',
                            widget=forms.Textarea(attrs={'rows': 2,}))


class CourtDivisionForm(BaseForm):
    class Meta:
        model = CourtDivision
        fields = ['office', 'name', 'is_active', 'legacy_code']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)


class CourtDistrictForm(BaseForm):
    class Meta:
        model = CourtDistrict
        fields = ['name', 'state', 'is_active']

    state = forms.ModelChoiceField(
        queryset=filter_valid_choice_form(
            State.objects.filter(is_active=True)),
        empty_label=u"Selecione")


class OrganForm(BaseForm):
    def __init__(self, *args, **kwargs):
        super(OrganForm, self).__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)
        for field_name, field in self.fields.items():
            if field_name == 'cnpj':
                field.initial = self.instance.cpf_cnpj

    cpf_cnpj = BRCNPJField(
        label="CNPJ",
        widget=forms.TextInput(attrs={'data-mask': '99.999.999/9999-99'}),
        required=False,
    )

    court_district = forms.CharField(
        label="Comarca",
        widget=TypeaHeadForeignKeyWidget(
            model=CourtDistrict,
            field_related='name',
            name='court_district',
            url='/processos/typeahead/search/comarca'))

    class Meta:
        model = Organ
        fields = ['office', 'legal_name', 'cpf_cnpj', 'court_district', 'is_active', 'legacy_code']


class CourtDistrictComplementForm(BaseForm):
    court_district = forms.CharField(label="Comarca",
                                     required=True,
                                     widget=TypeaHeadForeignKeyWidget(model=CourtDistrict,
                                                                      field_related='name',
                                                                      name='court_district',
                                                                      url='/processos/typeahead/search/comarca'))

    class Meta:
        model = CourtDistrictComplement
        fields = ['office', 'name', 'court_district', 'is_active', 'legacy_code']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)
