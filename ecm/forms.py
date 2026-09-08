# -*- coding: utf-8 -*-
# Author: Christian Douglas <christian.douglas.alcantara@gmail.com>
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Attachment, DefaultAttachmentRule
from core.forms import BaseModelForm
from core.utils import filter_valid_choice_form, get_office_field, get_office_session
from core.models import City, State, Person
from core.widgets import TypeaHeadForeignKeyWidget
from lawsuit.models import CourtDistrict
from task.models import TypeTask


class UploadFileForm(forms.Form):
    """ This form represents a basic request from Uploader.
    The required fields will **always** be sent, the other fields are optional
    based on your setup.
    Edit this if you want to add custom parameters in the body of the POST
    request.
    """
    file = forms.FileField()
    object_id = forms.CharField()
    model_name = forms.CharField()
    qqpartindex = forms.IntegerField(required=False)
    qqchunksize = forms.IntegerField(required=False)
    qqpartbyteoffset = forms.IntegerField(required=False)
    qqtotalfilesize = forms.IntegerField(required=False)
    qqtotalparts = forms.IntegerField(required=False)


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = '__all__'


class DefaultAttachmentRuleForm(BaseModelForm):
    name = forms.CharField(label="Nome",
                           required=True)

    description = forms.CharField(
        label=u'Descrição',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control input-sm',
                                     'rows': '2'})
    )

    type_task = forms.ModelChoiceField(
        queryset=filter_valid_choice_form(TypeTask.objects.all()).order_by('name'),
        empty_label='',
        required=False,
        label='Tipo de Serviço',
    )

    person_customer = forms.CharField(label="Cliente",
                                      required=False,
                                      widget=TypeaHeadForeignKeyWidget(model=Person,
                                                                       field_related='legal_name',
                                                                       name='person_customer',
                                                                       url='/client_form'))

    state = forms.ModelChoiceField(
        queryset=filter_valid_choice_form(State.objects.all()),
        empty_label='',
        required=False,
        label='UF',
    )

    court_district = forms.CharField(label="Comarca",
                                     required=False,
                                     widget=TypeaHeadForeignKeyWidget(model=CourtDistrict,
                                                                      field_related='name',
                                                                      forward='state',
                                                                      name='court_district',
                                                                      url='/processos/typeahead/search/comarca'))

    city = forms.CharField(label="Cidade",
                           required=False,
                           widget=TypeaHeadForeignKeyWidget(model=City,
                                                            field_related='name',
                                                            name='city',
                                                            url='/city/autocomplete/'))

    class Meta:
        model = DefaultAttachmentRule
        fields = ('office', 'name', 'description', 'type_task', 'person_customer', 'state', 'court_district', 'city')

    def clean(self):
        cleaned_data = super().clean()
        type_task = cleaned_data.get('type_task')
        person_customer = cleaned_data.get('person_customer')
        state = cleaned_data.get('state')
        court_district = cleaned_data.get('court_district')
        city = cleaned_data.get('city')

        if not type_task and not person_customer and not state and not court_district and not city:
            raise forms.ValidationError(_(u"Deve ser informado pelo menos um dos seguintes campos:"
                                          u" Tipo de Serviço," + chr(12) +
                                          u" Cliente,"
                                          u" UF,"
                                          u" Comarca"
                                          u" ou Cidade"))
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)
        self.fields['type_task'].queryset = filter_valid_choice_form(TypeTask.objects.filter(
            is_active=True, office=get_office_session(self.request))).order_by('name')        


class DefaultAttachmentRuleCreateForm(DefaultAttachmentRuleForm):

    def __init__(self, *args, **kwargs):
        self.documents_required = True
        super().__init__(*args, **kwargs)
