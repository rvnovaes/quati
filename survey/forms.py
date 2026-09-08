from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Survey
from core.forms import BaseModelForm, BaseForm
from core.utils import get_office_field


class SurveyForm(BaseForm):

    data = forms.CharField(label=_('Conteúdo'), widget=forms.HiddenInput())

    class Meta:
        model = Survey
        fields = ['office', 'name', 'data', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)
        self.order_fields(['office', 'name', 'data'])
