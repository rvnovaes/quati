from django.urls import reverse_lazy
import django_tables2 as tables

from core.tables import CheckBoxMaterial
from .models import DefaultAttachmentRule


class DefaulAttachmentRuleTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        sequence = ('selection', 'name', 'description', 'type_task', 'person_customer', 'state', 'court_district',
                    'city')
        model = DefaultAttachmentRule
        fields = ('selection', 'name', 'description', 'type_task', 'person_customer', 'state', 'court_district',
                    'city')
        attrs = {"class": "table stable-striped table-bordered"}
        empty_text = "Não existe regra de anexo padrão cadastrada."
        row_attrs = {
            'data_href': lambda record: reverse_lazy('ecm:defaultattachmentrule_update', args=(record.pk,))
        }
        order_by = 'name'